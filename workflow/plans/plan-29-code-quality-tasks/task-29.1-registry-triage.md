---
gmd: "0.1"
id: task-29.1-registry-triage
title: "Task 29.1: triage the open bug registry — every not-fixed row ends scheduled, deferred or closed, and a checker fails on a bare open"
tags: [task, plan-29, registry, bugs, triage, governance, code-quality]
metadata:
  node_type: task
  status: pending
  plan: plan-29-code-quality
  created: 2026-11-14
  updated: 2026-11-14
---

# Task 29.1: triage the open registry {#root}

> Plan: [[plan-29-code-quality]] ([[plan-29-code-quality#t1]])
> Status: Pending
> Depends on: the 0.83.0 deploy and the seven frozen spec-branch merges
> ([[plan-29-code-quality#decisions]] D2). The merges must land first, because a `scheduled` row
> has to name a task spec that exists on `master`, and several owners (the T0 sweep spec, the
> 25.1b and 16.5 revisions) arrive with those merges.
> Runs first in plan-29's order: 29.1 → 29.4 → 29.5 → 29.2 ∥ 29.3 ([[plan-29-code-quality#order]]).

rel: part-of -> [[plan-29-code-quality]]
rel: implements -> [[plan-29-code-quality#t1]]
rel: depends-on -> [[bug_registry#registry]]
rel: depends-on -> [[plan-review-2026-11-13#p1]]
rel: depends-on -> [[plan-review-2026-11-13#queue]]
rel: reinforces -> [[feedback_verify_fix_reachable_from_master]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: reinforces -> [[feedback_compare_failures_by_error_not_name]]
rel: related-to -> [[task-29.4-suite-health]]
rel: related-to -> [[task-29.5-split-giant-modules]]

## Why {#why}

The registry is how this project avoids re-deriving a known fix. It has 238 rows, and 81 of them
are not fixed. Many of those rows already have an owner, but the owner is recorded somewhere
else: a track table in [[plan-review-2026-11-13#p1]], an L-row, or a free-text note in the row
itself, such as `open (→ 26.5)` or `open (after 3.7 merges)`. Nothing can check those notes. A
bare `open` says neither who fixes the row nor when anyone will look at it again. This task
gives every not-fixed row exactly one machine-checkable outcome, then adds a check that keeps it
that way. {#why-body}

## Measured at `f3709d2` (2026-11-14) {#baseline}

Counted with a parser that skips `|` inside code spans and honours `\|`. Splitting on every `|`
miscounts the rows that quote `|| true` or `\|`. The status is the 7th cell. The count was made
twice, by two parsers written independently (the first draft's and this revision's); both give
the numbers below. The second run's output, with every not-fixed row's id, line and status, is
`workflow/review-output/plan29a-registry-count.log`; the parser is
`workflow/measurements/plan-29-spec-census/registry_count.py` ([[plan-29-spec-census]]).

| Measure | Value |
|---|---|
| registry rows (`\| bug-NNN \|`) | 238 (ids 001-240; 138 and 175 absent) |
| closed (`fixed` 156, `remedied` 1) | 157 |
| **not fixed** | **81** (the plan counted 80 at `0db6314`; bug-240 was added at `f3709d2`) |
| ... `open` (bare, or `open` + a note) | 73 |
| ... `recurring` | 5 (091, 168, 170, 209, 231) |
| ... `fix on branch (undeployed)` | 2 (085, 087) |
| ... `suspected` | 1 (218) |
| malformed rows (≠ 8 cells) | 3: bug-081 has 10 cells (a stray `\|` outside a code span); bug-085 and bug-088 have 7 (no `Seen` cell) |
{#baseline-table}

"Not fixed" here means the status cell does not start with `fixed`, `closed`, `wontfix`,
`not a bug`, `superseded` or `remedied`. That is the lead's definition. The checker in
[[#r4]] uses the grammar in [[#r1]] instead. {#baseline-def}

## Requirements {#requirements}

### R1: one status grammar {#r1}

The registry's `#status` table is replaced by this grammar. Every row's status cell must match
one form. `→` and `->` are both accepted.

| Form | Meaning | Required parts |
|---|---|---|
| `fixed …` / `remedied …` | closed by a fix in this repo (all 157 existing forms stay valid) | unchanged; existing rows are not rewritten |
| `scheduled → <target> (<track>)[; <note>]` | a named task or plan will fix it | `<target>` is the frontmatter `id` of a file under `workflow/plans/`. `<track>` is one of `T0`..`T6` ([[plan-review-2026-11-13#p1]]) or `P29` (plan-29). |
| `deferred: <reason>; review <YYYY-MM-DD>[; <note>]` | nobody owns it yet, on purpose | a reason of at least 4 words; a review date no more than 183 days after the checker's `--today` (default: the current date). This bound moves forward with the calendar, so it cannot turn a green suite red; a date that has passed is `--overdue`'s business ([[#r4]]) |
| `closed: <evidence>` | will not be fixed here, or was fixed elsewhere | one of the [[#r3]] evidence shapes |
| `recurring; scheduled → …` / `recurring; deferred: …` | seen again after a fix | `recurring` alone is no longer a complete status |

`open` and `suspected` are not in the grammar. After this task, no row holds them. A new bug is
logged as `scheduled` or `deferred` on the day it is logged. If its owner is unknown, it is
`deferred: owner not yet chosen; review <date + 14 d>`. The rule in
`.claude/rules/bug-registry.md` changes to say this. {#r1-body}

**Other specs that write a status.** A task that sets a registry status after this one uses the
grammar. One approved spec does not yet: the T0 suite-trust sweep (`task-t0-suite-trust-sweep`,
approved on branch `spec-wave-t0` at `fa1227d`, not yet on `master`; track T0 in
[[plan-review-2026-11-13#p1]]). Its T0.3 sets
`open / diagnosed-loud` for a flake it could not fix or reproduce. Under this grammar that row
reads `deferred: diagnosed-loud, <trial counts>; review <date>` (a flake that now explains
itself, with no owner until it fires again), or `scheduled → <target>` when T0.3 opens a product
row for it. T0 runs after plan-29, so the triage does not edit T0's rows; it adds one amends
line to the T0 spec ([[#files]]) so the two specs do not disagree. A search of
`workflow/plans/` for other status writers is step 0 of [[#r2]]. {#r1-other-writers}

### R2: the procedure {#r2}

The triage runs once over the 81 rows, in the order of [[#starting-map]].

0. **Re-count, and find the other writers.** Run the count again at the task's base sha (rows
   are added daily: bug-233 to bug-240 arrived in one day). The summary records the new total and
   the ids added since `f3709d2`. Then list every spec under `workflow/plans/` that writes a
   registry status that is not in [[#r1]] (`grep -rn "diagnosed-loud\|status .open" workflow/plans`
   is the starting query) and give each an amends line.
1. **Read the row and its recorded owner.** The owner may be in the row's text, in the track table
   [[plan-review-2026-11-13#p1]], in an L-row of [[plan-review-2026-11-13#lead]], or in a task
   spec's "Inherited" section. Use `rmx-master query "mentions:bug-NNN"` and plain file reads.
2. **If an owner is recorded and its spec exists on `master`:** write `scheduled → <id> (<Tn>)`,
   using the track from the table. A recorded owner whose spec does not exist yet (a stub named
   in a queue line only) is written as `deferred: owner <name> has no spec yet; review <date>`.
   It is never written as `scheduled`. A `scheduled` target is the most specific spec that
   exists: a task spec when there is one, a plan file only when the plan has no task spec for
   that work yet (the reviewer checks this; the checker cannot).
3. **If no owner is recorded,** pick one, the way the user would, using the track rule in
   [[plan-review-2026-11-13#p5]]: "a new bug joins its owning task's track". The owning task is
   the queued task whose files and concern the bug touches. Record the reason in the row's note
   (`; L-row Lnnn` or `; triage 29.1: touches <file> which <task> rewrites`). If no queued task
   fits, the row is `deferred` with a reason and a review date.
4. **If the row may already be fixed** (`fix on branch`, `after 3.7 merges`, `0.83.0 must land
   this`), apply the [[#r3]] evidence bar. If the bar is met, write `closed: …`. If not, the row
   stays in the queue under its owner.
5. **User-deferred rows** (bug-088, bug-101: "stay deferred by the user") become
   `deferred: by the user (<date of the decision>); review <date>`. The review date is the next
   date the queue revisits them; if none is recorded, it is the date plan-29 closes plus 30 days.
   That date is written as an absolute date.
6. **One owner per row.** A row named by two tracks is split into two rows, never given two
   statuses. Example: bug-085 is "fix on branch" for the Lance batching and "compaction open" for
   the store surgery. The new row takes the next free id and carries `split from bug-NNN`.
7. **Malformed rows are repaired** to exactly 8 cells (bug-081, bug-085, bug-088). The text is
   kept; only cell boundaries change.

### R3: the evidence bar for `closed` {#r3}

A row is `closed` only with one of these four shapes. "It looks fixed" is not one of them.

| Shape | Status text | What must be true, and is checked |
|---|---|---|
| (a) fixed elsewhere | `closed: fixed <sha> (<test node id>)` | `git merge-base --is-ancestor <sha> master` succeeds, which is the [[feedback_verify_fix_reachable_from_master]] rule. The named test exists at `master`. Its RED run is either already recorded in that task's summary, or it is run now: revert the fix in a throwaway clone, see the test fail, and cite the log. |
| (b) reproduced as gone | `closed: not reproduced at <sha>; <log path>` | The row's own reproduction is run at `<sha>` and the log is cited. A load- or timing-dependent row (tags `flaky`, `load`, `timing`) can NOT close this way. A non-reproduction proves nothing about a flake. It goes to its owner ([[task-29.4-suite-health]] for 228/229/231) instead. |
| (c) code removed | `closed: code removed at <sha>` | The function or file named in the row's `File(s)` cell is absent at `master`. The checker greps for the name. |
| (d) superseded | `closed: superseded by bug-NNN` | bug-NNN exists, is not itself `closed: superseded`, and names this row in its text. |
{#r3-table}

A `fixed` row whose fix was never deployed stays as it is: `fixed` means "landed on master", and
deploying is a separate fact. The two `fix on branch (undeployed)` rows are closed only by shape
(a), and only if the branch merged. {#r3-deploy}

### R4: the checker {#r4}

There is one script, `scripts/check-bug-registry.py`, with no third-party imports.

- It parses the `#registry` table with a code-span-aware cell splitter. It fails on any row that
  does not have exactly 8 cells, and names that row.
- It fails on any status outside the [[#r1]] grammar. Each failure line names the id and the
  status found (for example `bug-123: status "open" is not in the grammar`). It never stops at the
  first failure.
- `scheduled → <target>` is resolved against the frontmatter ids of `workflow/plans/**/*.md`. An
  unresolved target fails, and the line names the target.
- `closed:` shape (a) runs `git merge-base --is-ancestor <sha> HEAD`, with a timeout. A git failure
  is reported as `could not verify`, and the checker then exits non-zero. It never treats a git
  error as "not found" (the bug-225 r3 lesson). Exit 1 with empty stderr is the only "not an
  ancestor" answer. Until 29.3 ([[plan-29-code-quality#t3]]) lands its `run_git` helper the
  checker carries its own six-line runner; 29.3's census then lists this script as one of the
  callers to move.
- `--history-against <git-rev>` compares the registry with the one at `<git-rev>` and fails on any
  row whose non-status cells changed ([[#ac-6]]). It is a mode, not a suite test: a test that
  needs a particular parent commit stops meaning anything one commit later.
- **Exit codes:** 0 = clean; 1 = findings; 2 = could not run (no registry, unreadable file).
- `--overdue` additionally lists `deferred` rows whose review date has passed, and exits 1 if any
  do. This is not part of the suite, because a test that fails when the calendar moves is a
  wall-clock test. The CLAUDE.md `#cleanup-phase` step runs it after each plan.

### R5: registry docs follow {#r5}

- `bug_registry.md#status` holds the [[#r1]] table.
- `.claude/rules/bug-registry.md` says: "log a new bug as `scheduled → <task>` or
  `deferred: …; review <date>`; never a bare `open`".
- `./scripts/lint-gmd.sh` gains no new step. The checker runs as a pytest test ([[#ac-4]]), so the
  suite gates it, and `CLAUDE.md#before-commit` names the script once.

## Starting map (recorded owners at `f3709d2`) {#starting-map}

This table is the triage's input, not its result. It groups the 81 rows by the owner already
recorded for them. Step 2 of [[#r2]] confirms each one. "Closed?" rows are checked against
[[#r3]].

| Recorded owner (source) | Rows | n |
|---|---|---|
| T0 sweep ([[plan-review-2026-11-13#p1]]; 196 by L48) | 091, 127, 130, 168, 170, 190, 196, 215 | 8 |
| deferred by the user ([[plan-review-2026-11-13#p1]]) | 088, 101 | 2 |
| T1 0.83.0 / 25.1 rev 7 (shipped): closed? | 164, 181 | 2 |
| T2: 26.5 (+208, 213, 220 per L37); backlog 206, 210 | 206, 208, 210, 213, 220 | 5 |
| T3: 19.0 (100, 103, 104); 25.1b (182 R15 per L44; 224 per L68); backlog 165, 166 (L43) | 100, 103, 104, 165, 166, 182, 224 | 7 |
| T4: bug-185 (+186), 23.x (099, 106, 136, 177), 16.6 slice (120), plan-18 18.3 R8 (123, named in its own row); backlog 097, 207 | 097, 099, 106, 120, 123, 136, 177, 185, 186, 207 | 10 |
| T5: 16.5 (081, 102, 167, 174 closed by 16.5; 222 = 16.5 R2 per L48); backlog 180 | 081, 102, 167, 174, 180, 222 | 6 |
| T6: 218, 219, 086, 107; backlog 119, 121, 124 | 086, 107, 119, 121, 124, 218, 219 | 7 |
| plan-29 ([[plan-29-code-quality#tasks]]): 29.4 (228, 229, 231; 239 the README suite count); 29.3 (223 broad except, 233 git runner, 234/236/238 query terms); 29.2 (235) | 223, 228, 229, 231, 233, 234, 235, 236, 238, 239 | 10 |
| row says the fix landed or is due: closed? | 085 (split, R2.6), 087, 188 (3.7 merged), 189 (3.7 merged), 209 ("0.83.0 must land this") | 5 |
| **no recorded owner: triage decides** | 055, 075, 089, 096, 125, 151, 152, 153, 154, 161, 169, 194, 201, 203, 221, 226, 232, 237, 240 | 19 |
| **total** | | **81** |
{#starting-map-table}

Suggestions for the 19 unowned rows. They are not decisions; step 3 of [[#r2]] makes them:
- **221** (stale `rel` edge after a re-ingest) is bug-216 family → T6.
- **226** (reingest's memory-partition probe) is bug-135 family. It is the
  [[feedback_converge_repeated_shapes]] case → 29.3, or T6.
- **232** (tracked-catalog remedies) is the shape [[plan-29-code-quality#why]] cites, "one check
  shared by callers with different needs" → 29.3.
- **237** (query cost) sits with 234/236/238 → 29.3 or 29.2. It needs a measurement first.
- **201, 203** (sync output and route) → T2 26.x or T4.
- **151-154** (refine/curator) and **161** (hub wedge) have no queued owner; they are likely
  `deferred`.
- **075** (GMD ranking) is named by [[task-21.4-surfaces-and-nl-ranking]] → T3, if that spec
  takes it as a requirement and not only as context.
- **055** is named only by plan-13 (`drafting`, dormant) → `deferred`, or `closed` by shape (b)
  if its measurement no longer reproduces; its tags say `unverified`.
- **240** (`rmx ingest <file>` ingests nothing, exit 0) is a silent failure on a memory path. It
  goes to T4 (the ingest write path), not to the backlog.
- **096, 201** are CLI output and exit-code rows in `cli.py`. They are fixed after
  [[task-29.5-split-giant-modules]], in the module the split gives them, so they are
  `scheduled` only if an owning task exists and `deferred` with the 29.5 close date as the review
  date if not.
{#starting-map-hints}

## Acceptance criteria {#acceptance}

- **AC-1: no bare `open`.** `scripts/check-bug-registry.py` exits 0 on the triaged registry.
  Every one of the 81 rows (plus any row added before the triage commit) matches [[#r1]], and no
  status is `open`, `suspected` or `recurring` alone. {#ac-1}
- **AC-2: every `scheduled` names a real task.** Each target resolves to a frontmatter id under
  `workflow/plans/` at the triage commit, and its track is the one [[plan-review-2026-11-13#p1]]
  gives that task (or `P29`). The checker verifies the resolution. A reviewer verifies the track
  against the table: the checker cannot know the table, and the summary says so. {#ac-2}
- **AC-3: every `closed` meets the bar.** Each `closed:` row names its [[#r3]] shape. Every shape
  (a) sha is an ancestor of `master`, and the checker runs this. Shape (b) cites a log that
  exists. No row tagged `flaky`/`load`/`timing` is closed by shape (b); the checker enforces this
  from the Tags cell. {#ac-3}
- **AC-4: the checker fails on what it must fail on.** `tests/test_bug_registry_triage.py` runs the
  script on:
  - the real registry, which must exit 0;
  - a must-fail fixture registry (`tests/fixtures/bug_registry_mustfail.md`) holding one row per
    failure class: a bare `open`; `recurring` alone; `suspected`; `scheduled → task-does-not-exist`;
    `deferred:` with no review date; `closed: fixed <sha not in history>`;
    `closed: not reproduced …` on a row tagged `flaky`; a 7-cell row; a 10-cell row.

  The test asserts exit 1 and that EACH class is named in the output. A checker that stops at the
  first finding fails this test.
  - **RED:** at `master` the script does not exist, so the test fails. That run is recorded.
  - **Mutations:** each must turn the test RED, and each is recorded in the summary:
    1. drop the `open` check;
    2. split on every `|` (the naive splitter);
    3. accept any target;
    4. treat a git error as "not an ancestor";
    5. let the first failure return early;
    6. `--history-against` compares only the Status cell (the lost-word fixture goes green, so
       the test is red).
  {#ac-4}
- **AC-5: counts in the summary.** `workflow/implementation_summaries/task-29.1-registry-triage.md`
  holds:
  - a triage table with one row per bug: id, old status, new status, and the evidence or reason;
  - counts per outcome: scheduled per track, deferred, closed per shape, rows split;
  - the before/after not-fixed counts, re-measured at the triage commit's parent and at the
    commit. These must be 81 + any rows added meanwhile, and 0 bare `open`.
  {#ac-5}
- **AC-6: no row loses its history.** For every changed row, every cell except Status is
  byte-identical to its pre-triage text. Text is appended to Status, never removed from it. For
  example, `open (→ 26.5)` becomes
  `scheduled → task-26.5-memory-organise-verb (T2); was open (→ 26.5)`.
  - **Checked once, on the real registry:** `scripts/check-bug-registry.py --history-against
    <triage commit>^` exits 0, and its output is logged in the summary.
  - **Exceptions, each named in the output:** the three repaired rows (081, 085, 088) are
    compared as the row text with cell delimiters removed, because only their boundaries change;
    a split row's new sibling is compared with the part of the old row it took.
  - **Proven by fixture, in the suite:** the test builds two small registries in a tmp git
    repository: one where only Status changed (exit 0) and one where a Root-cause cell lost a
    word (exit 1, naming the id and the cell).
  {#ac-6}

## Test strategy {#test-strategy}

This is a docs task, so its proof is the checker. The checker is new code, so it is TDD:
- **RED:** `tests/test_bug_registry_triage.py` is written first. It fails because the script is
  missing, and it is recorded failing.
- **GREEN:** the script is written.
- The triage edits the registry until the real-registry case is green.

The must-fail fixture follows [[feedback_clean_corpus_hides_a_dead_gate]]: a checker that only
ever saw a clean registry could pass while having stopped checking anything.

The mutation list is in [[#ac-4]].

Output goes to `workflow/review-output/task-29.1-*.log`, as the `enforce-test-to-file` hook
requires. {#test-strategy-body}

## Files {#files}

| File | Change |
|---|---|
| `workflow/bug_registry.md` | `#status` grammar; 81 status cells; 3 malformed rows repaired; split rows appended |
| `scripts/check-bug-registry.py` | new: the checker ([[#r4]]) |
| `tests/test_bug_registry_triage.py` | new: the real-registry case, the must-fail fixture, the history check |
| `tests/fixtures/bug_registry_mustfail.md` | new: one row per failure class |
| `.claude/rules/bug-registry.md` | new-bug status rule ([[#r5]]) |
| `CLAUDE.md` | `#before-commit` names the checker; `#cleanup-phase` runs `--overdue` |
| `workflow/implementation_summaries/task-29.1-registry-triage.md` | new: the triage table and counts |
| `workflow/plans/task-t0-suite-trust-sweep.md` | one amends line: `open / diagnosed-loud` reads as [[#r1-other-writers]] says (after that spec's branch has merged) |
{#files-table}

`CLAUDE.md` and `.claude/rules/bug-registry.md` are instruction files. Their two edits are part
of what the user approves with this plan; the implementer makes exactly the edits named here and
quotes the diff in the summary. {#files-instruction-note}

## Out of scope {#out-of-scope}

- **Fixing any bug.** A row closes only by evidence that already exists or by running its
  reproduction.
- **Rewriting the 157 closed rows.**
- **Changing the queue order.** A triage that wants to move a queued task asks the lead. A queue
  insertion is a user decision with a Q-id ([[plan-review-2026-11-13#p5]]).
- **Live-store work.** Reproductions run in a littlebig clone or on a throwaway store.
{#out-of-scope-list}

## Decisions taken in this spec {#decisions}

- **plan-29 D7 (spec, as the user would):** `deferred` carries a review date, and the overdue
  check runs at cleanup, not in the suite.
  - **Why:** a suite test that turns red when the date passes is a wall-clock test. 29.4 forbids
    those.
  - **Why it still has a review date:** a `deferred` with no date is the bare `open` under
    another name.
- **plan-29 D8 (spec):** load- and timing-dependent rows cannot close on a single
  non-reproduction ([[#r3]] (b)).
  - **Why:** bug-228 passed 8/8 alone and then failed in three full suites.
    [[feedback_compare_failures_by_error_not_name]] applies.
- **plan-29 D9 (spec):** `open` leaves the grammar for new rows too, not only for the 81.
  - **Why:** the task's check is "no bare `open`". A grammar that still admits `open` for
    tomorrow's row makes the check pass today and mean nothing next week.
  - **Cost:** logging a bug takes one more decision (an owner, or a review date 14 days out).
    The low threshold to log stays: `deferred: owner not yet chosen; review <date>` is always
    available and takes no thought.
{#decisions-list}

## Revision note (2026-11-14, second author) {#rev-note}

The first draft of this spec was written by an agent that was stopped before committing. This
revision kept it after re-checking it: the row counts were re-made with a second parser (same
numbers), and the starting map was checked against [[plan-review-2026-11-13#p1]] and the queue,
and for the 19 unowned rows against every file under `workflow/plans/`. Changed: [[#ac-6]] no
longer depends on a parent commit inside the suite; [[#r1-other-writers]] and step 0 of [[#r2]]
are new; the review-date bound is relative, not a fixed date; hints for 055, 075, 096, 201 and
240 were added; plan-29 D9 records a choice the draft made without naming it. {#rev-note-body}
