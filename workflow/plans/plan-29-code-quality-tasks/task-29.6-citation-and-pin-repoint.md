---
gmd: "0.1"
id: task-29.6-citation-and-pin-repoint
title: "Task 29.6: re-point the specs — every cli.py / store.py line citation becomes a symbol, every pin keyed on those files is rewritten with its owner's check, and a census keeps it so"
tags: [task, plan-29, specs, citations, pins, repoint, cli, store, code-quality]
metadata:
  node_type: task
  status: pending
  plan: plan-29-code-quality
  created: 2026-11-14
  updated: 2026-11-14
---

# Task 29.6: re-point citations and pins {#root}

> Plan: [[plan-29-code-quality]]. This task is new: ruling L105 (2026-11-14) created it from
> ch-bsd's finding that the citation and pin pass had no task (`bsd-plan29-spec-r1#b3`). The
> plan's `#tasks` and `#order` gain its row in the merge that lands these specs (the lead's).
> Status: Pending
> Depends on: [[task-29.5-split-giant-modules]] (its symbol map, its `tools/repoint_citations.py`
> and its dry run); 29.2 and 29.3 (`task-29.2-mypy-gate`, `task-29.3-converge-shapes`), because
> lines move again in both and 29.3 renames helpers.
> Runs last in plan-29's order: 29.1 → 29.4 → 29.5 → 29.2 ∥ 29.3 → **29.6**.
> Docs-only, plus one census test. It edits other tasks' specs: [[#r6]] says under what rule.
> User gates: none. Open decisions it waits on: none. plan-29 D17 is decided (L106): `daemon.py`
> and `ingest.py` are not split by 29.5, and `verbs.py` only if its assessment passes ([[#r0]]).

rel: part-of -> [[plan-29-code-quality]]
rel: depends-on -> [[task-29.5-split-giant-modules]]
rel: depends-on -> [[tdd-governance]]
rel: related-to -> [[task-29.1-registry-triage]]
rel: related-to -> [[task-29.4-suite-health]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: reinforces -> [[feedback_read_identifiers_at_write_time]]

Other documents are cited as in [[task-29.4-suite-health#citing]]: **T0**, the **queue**,
**store** and **memory reviews**, the ch-bsd report `bsd-plan29-spec-r1` (dev `master`,
`549458e`) and the sibling specs 29.2 and 29.3 are not on this spec's branch, so their ids and
anchors are written as code. {#citing}

## Why {#why}

After 29.5, `src/refmatrix/cli.py` does not exist and `store.py` holds a fifth of what it held.
Approved specs that have not been built still say `cli.py:9818` and `store.py:4381`. Seven of
them go further and **pin** a check to those files: "walk every `src/refmatrix/*.py`", "exempt
`cli.compact`", "the AST of `store.py`". A citation that points nowhere costs the next reader
ten minutes. A pin that points nowhere passes: its corpus is empty, and an empty corpus is
clean ([[feedback_clean_corpus_hides_a_dead_gate]]). {#why-body}

29.5 builds the tool and publishes the map, and does not rewrite a single spec, because 29.2
and 29.3 move lines again and 29.3 renames helpers. This task is the rewriting, done once,
after them. Until it is done, the window in which those specs name a file that is not there
is open; [[task-29.5-split-giant-modules#r8]] states that window and what a task that cannot
wait does about it. {#why-when}

## Measured at `f3709d2` (2026-11-14) {#baseline}

From `workflow/review-output/plan29a-citation-census.log` (script
`workflow/measurements/plan-29-spec-census/citation_census.py`, [[plan-29-spec-census]]) and
from the three reviews. Everything is re-counted at this task's base ([[#r0]]).

| Measure | Value | Source |
|---|---|---|
| `cli.py:NNNN` in `workflow/plans/` | 234 sites, 45 files | census log |
| `store.py:NNNN` in `workflow/plans/` | 134 sites, 27 files | census log |
| ... in specs whose `metadata.status` is not completed, both modules | **271 sites, 44 files** | census log (`master` only) |
| ... counting the spec-branch copy where one exists | 280 sites in 53 documents; 249 in 50 once three shipped specs with stale frontmatter are set aside | queue review `#p29-3` |
| `daemon.py:NNNN` / `verbs.py:NNNN` / `mcp.py:NNNN` in not-completed specs on `master` | 128 / 55 / 9 = **192** sites (in 25 / 17 / 3 files) | the same method as the 271: `git show f3709d2:<spec>` for every spec under `workflow/plans/` whose `metadata.status` is not completed |
| ... the same three, counting the spec-branch copy where one exists | 142 / 58 / 9 = 209 | queue review `#p29-3` |
| line citations in `docs/` | `cli.py` 8, `store.py` 13 | census log |
| line citations in history (all of `workflow/`, `review-output/` excluded) | `cli.py` 759 in 224 files; `store.py` 394 in 114 | census log |
| heaviest unbuilt specs | 23.1 (35), 19.0 (32), 22.6 (27), 25.1 (19; shipped, frontmatter stale), 17.1 (12) | census log |
{#baseline-table}

**The pins** (store review `#ast-pins-break-under-29-5`, memory review `#s31`, queue review
`#p29-3`):

| Spec | Pin | Kind |
|---|---|---|
| 18.2 | R11, R13, AC-17: walk "EVERY `src/refmatrix/*.py`" with exemptions by qualified name | non-recursive walk; qualified names |
| 18.3 | AC-14: the same walk; exempts `cli.compact`, `store.Store.rebuild_entities_indexes` | non-recursive walk; qualified names |
| 22.1a | AC-8c | keyed on the file `store.py` or `cli.py` |
| 22.2 | the `ingest_ok` and `restored_from` pins | keyed on the file |
| 22.6 | AC-6f | keyed on the file |
| 16.6 | AC-9c, AC-9d, AC-12 | keyed on the file |
| bug-218 | AC-2, AC-4b | keyed on the file |
| 26.5 | "wrap `run` at `daemon.py:3376`" (L63) | a requirement that depends on a location |
| 23.1 | 33 `store.py` sites, some inside requirements | requirements that depend on locations |
| 21.2 | three of its nine frozen gold files are `cli.py` or `store.py` | frozen data keyed on the files |
{#baseline-pins}

## Requirements {#requirements}

### R0: re-count, and check the map before trusting it {#r0}

At the task's base sha, which holds 29.5, 29.2 and 29.3:

1. Re-run the census. The summary shows the numbers of [[#baseline]] beside the new ones, per
   spec.
2. **Verify the symbol map against the tree.** `tools/split_maps/symbol_map.json` was written by
   29.5; 29.2 and 29.3 have since renamed and moved things. `tools/repoint_citations.py
   --verify-map` checks that every `new module :: symbol` in the map resolves at the base sha
   (by syntax tree). A row that does not is corrected first, with its evidence: the commit that
   renamed or moved it (`git log -S`), or the rename tables in 29.2's and 29.3's summaries. No
   spec is rewritten from a map that has an unresolved row.
3. **Read what 29.5 did with `verbs.py`.** plan-29 D17 is decided: `daemon.py` and `ingest.py`
   are not split by 29.5; `verbs.py` is split only if its assessment passed. If it was, its
   moves are in the map, `verbs.py:N` joins `cli.py:N` and `store.py:N` as a citation of a file
   that no longer exists as cited, and the census of [[#r7]] forbids it too.
4. **Start from 29.5's dry run** ([[task-29.5-split-giant-modules#ac-8]]), re-run at this base:
   per spec, what resolves, what does not, and the pins.
5. **Classify every spec that has a hit** as one of:
   - **cite-only:** its citations sit in prose, facts or "where" columns; no requirement or AC
     depends on the location;
   - **location-bound:** a requirement or an AC names a location and would mean something else
     if the location were wrong (a pin; "wrap X at …"; an AC that greps a file);
   - **completed or history:** not rewritten ([[#r5]]).
   The classification is a table in the summary, with the sentence that made a spec
   location-bound quoted.

### R1: every line citation becomes a symbol {#r1}

For every spec under `workflow/plans/` whose `metadata.status` is not completed, and for
`docs/`:

- `cli.py:NNNN` and `store.py:NNNN` are rewritten by the tool to the def's home at the base sha,
  in the form `` `cli/<module>.py::<def>` `` or `` `store_<concern>.py::Store.<method>` ``.
- **The line is resolved at the commit that first wrote the citation, not at the spec's last
  change and not at `HEAD`.** For each site the tool finds the **oldest commit that added the
  exact token** and names the def that held line NNNN of the module **at that commit**
  ([[feedback_read_identifiers_at_write_time]]).
  - **The search is by the whole token, with a digit boundary:**
    `git log --reverse --follow -G'cli\.py:981([^0-9]|$)' -- <spec>`, the first hit. Not
    `-S'cli.py:981'`: pickaxe `-S` counts a substring, so a commit that added `cli.py:9818` is a
    hit for `cli.py:981` as well. With 271 sites over two modules such pairs are likely, and a
    spec that cites both would be resolved at the wrong commit with nothing to show it (ch-bsd
    r4 `#m2`; ruling L111).
  - Why not the spec's last-change sha: most specs are edited after their citations are
    written. Review folds, freshness passes, 29.1's amends lines and this task's own track
    commits all touch a spec without re-reading its citations, and `cli.py` moved about 1,200
    lines between `1cf3b9f` and `master`. A citation resolved at the last-change sha names the
    def that sat at that line when the spec was last touched: wrong, with nothing to show it
    (ch-bsd r2 `#ns4`).
  - Why not `git blame` on the line: a paragraph reflow moves the token to another line
    without changing it, and blame then names the reflow commit, which is the same mistake
    (ch-bsd r3 `#m2`). The token search follows the token, and its oldest hit is the commit
    that first wrote it, whatever reflowed it later. Blame (`-L <n>,<n>`) is the fallback only,
    for a token the search cannot place.
  - `-G` also hits a commit that only moved the token, so hits are not counted. The tool counts
    whole-token occurrences in the spec before and after each hit; a commit where the count
    goes up added it. A token added at more than one commit (removed and written again, or
    written twice) is resolved at each; it is rewritten only if they all name the same def,
    and listed as unresolved otherwise.
  - **A named symbol is checked.** Where the sentence that carries the citation names a symbol,
    the resolved def must be that symbol. A mismatch is listed as **unresolved**, with both
    names; it is not rewritten.
  - T0's R0.1 found `store.py:717` at `:1159` two weeks after it was written.
- **A site the tool cannot resolve is not guessed.** A line that was module-level code, a def
  that no longer exists, a spec whose last-change sha does not hold the file: each is listed.
  A person then resolves it by reading, or the spec's owner strikes the citation, and the
  summary records which.
- **Other modules' line citations** (`daemon.py:N`, `verbs.py:N`, `mcp.py:N`, and any module
  the tool is given) are rewritten to symbols in the same pass. Those files did not move, so no
  map is needed: the def that held the line at the spec's sha is named. They are in scope
  because they are stale today and a symbol does not rot (plan-29 D25).
- A rewritten citation keeps nothing of the old number. The map document
  (`docs/architecture/module-split-map.md`) is where an old `file:line` in history is resolved.

### R2: every pin is rewritten, with its owner's check {#r2}

A pin is a requirement. Rewriting it changes what a spec demands, so the tool does not do it.

1. **A walk over `src/refmatrix/*.py`** becomes "every module under `src/refmatrix`, recursive",
   and the spec says which census of 29.3's kit it is a family of, where one exists (store
   review `#plan29-converge-candidates`).
2. **An exemption by qualified name** (`cli.compact`,
   `store.Store.rebuild_entities_indexes`) is rewritten to the name the split gave it, taken
   from the map, in the `module:qualname` form the existing censuses use.
3. **A check keyed on the file `store.py` or `cli.py`** is re-keyed on the symbol it was about
   (the function or method), located by the map.
4. **Each rewritten pin gets its owner's freshness check.** The owner of the spec (the lead
   names one per track) re-reads the requirement against the code at the base sha and records
   one of: *holds as rewritten*; *holds, with this change* (the change is made and listed);
   *no longer applies* (the reason, and what replaces it). The record is a row in the summary
   with the owner's name and the date.
5. **A pin's synthetic bypass is restated.** Where the spec's AC has a must-fail case ("a
   `CHECKPOINT` in an unlisted module fails"), the case names a location that exists after the
   split, in the new form.

### R3: the location-bound requirements {#r3}

- **26.5:** "wrap `run` at `daemon.py:3376`" (L63). The owner states the symbol and confirms the
  wrap point still exists in that shape after 29.2 and 29.3.
- **23.1:** its 33 `store.py` sites. The tool rewrites them; the owner confirms each one that
  sits inside a requirement.
- **Every other spec** the R0 classification marks location-bound: the same check, the same
  record.
- A requirement that **no longer makes sense** after the split or after 29.2 / 29.3 (the code it
  wraps was converged away) is not rewritten into something plausible. It is raised to the
  lead as a spec revision for that task, and the summary lists it as open.

### R4: 21.2's gold files {#r4}

21.2 froze nine gold files; three are `cli.py` or `store.py` (memory review `#s31`). A frozen
answer that names a file that is gone cannot be matched. 21.2's owner chooses, per file: key
the gold on the **unique definition** (the symbol, by the map), or **re-freeze** after the
split. This task lists the three, records the choice and its date, and makes the edit when the
choice is "key on the definition". A re-freeze is 21.2's own work and is recorded here as
handed to it, with 21.2's spec amended to say so.

### R5: what is not rewritten {#r5}

Completed specs, implementation summaries, handoffs, the ch-bsd ledger and `review-output/` keep
their citations. They are a record of what was true when they were written. The map document
resolves them. A spec whose frontmatter says it is unbuilt but which has shipped (25.1, 26.1,
bug-178, bug-216 at `f3709d2`) is history: its frontmatter is corrected by the lead before this
task ([[task-29.1-registry-triage#r2]] step 0 lists them), and it is then left alone.

### R6: editing other tasks' specs {#r6}

- **A cite-only rewrite needs no ch-bsd re-approval** (queue review `#p29-3`). It changes no
  requirement. The commit lists, per spec, the number of sites rewritten, and the diff is the
  tool's.
- **A location-bound change is the owner's**, made by the owner or signed by the owner
  ([[#r2]] item 4), and gets a ch-bsd confirm-lite on the changed lines, in one round per
  track.
- **Approval status does not change.** An approved spec stays approved through a cite-only
  rewrite. A location-bound change that alters a requirement returns that spec to its owner's
  revision round, and the summary says which specs that happened to.
- **One commit per track** (T2, T3, T4, T5, T6, the T0 spec, `docs/`), so that a track's owner
  reviews one diff.
- **T0's R0.1 stays the rule** for every task that builds from a spec afterwards: re-verify
  every cited site at the branch base. A symbol makes that a lookup and not a search.

### R7: a census keeps it true {#r7}

`tests/test_spec_citation_census.py` runs `tools/repoint_citations.py --check` over
`workflow/plans/` and `docs/`:

- it fails on any `cli.py:<digits>` or `store.py:<digits>` in a spec that is not completed, and
  in `docs/`, naming the file and the line of the spec;
- it fails on any non-recursive `src/refmatrix/*.py` walk named in an unbuilt spec's
  requirement or AC (the phrase forms the pins used, listed in the tool);
- it fails on a `module.py::symbol` citation of `cli/*` or `store*` whose symbol does not
  resolve in the tree, so that a later rename cannot leave a dead symbol behind;
- **the allow list** holds only the sites [[#r1]] listed as unresolved and a person then kept on
  purpose, each with its reason. It is exact: an entry that matches nothing fails.

Line citations of other modules are not forbidden by the census: it counts them and prints the
count, and the spec template says to cite a symbol.

### R8: the template and the rule {#r8}

`workflow/templates/task-spec.md` gains one line under "Architecture References": a code
location is cited as `path/module.py::symbol`, never as `file:line`; a line number may follow in
parentheses with the sha it was read at. `workflow/PLANNING_WORKFLOW.md` says the same in one
sentence. Nothing else in the templates changes.

## Acceptance criteria {#acceptance}

- **AC-1: no dead file citation is left.** The census passes: no not-completed spec and no file
  under `docs/` matches `\b(cli|store)\.py:\d+`, except allow-listed sites. The summary gives,
  per spec, sites before, rewritten, unresolved-and-resolved-by-hand, and kept. The totals add
  up to R0's count. {#ac-1}
- **AC-2: every rewritten citation resolves.** For each rewritten site the symbol exists in the
  named module at the task's final sha (the census's third check). A sample is not enough: the
  check is over all of them. {#ac-2}
- **AC-3: the line was read at the right commit.** On a fixture repository: a spec is written at
  commit A citing `mod.py:10`, where line 10 holds `def f`. At commit B the spec is edited on a
  **different** line, and by B line 10 of `mod.py` holds `def g`. At commit C the citation's
  paragraph is **reflowed**, so the unchanged token `mod.py:10` now sits on another line of the
  spec. At `HEAD` line 10 holds `def h`.
  - the tool writes `::f`;
  - a tool that resolves at the spec's last-change sha, or by `git blame` on the line, would
    resolve at C and write `::g`; one that resolves at `HEAD` would write `::h`: the fixture
    fails on each;
  - a second citation whose sentence names `f` while its line resolves to `g` is listed as
    unresolved and is not rewritten;
  - a third citation whose token was added at two commits where line 10 held different defs
    is listed as unresolved, with both;
  - **a token beside a longer one:** the spec also cites `mod.py:100`, added at a later commit D,
    where line 100 holds `def k`. `mod.py:10` is resolved at A (`::f`) and `mod.py:100` at D
    (`::k`). A tool that searches for the substring (`-S'mod.py:10'`) also hits D and fails
    this row.

  29.5 tests the tool on the same fixture ([[task-29.5-split-giant-modules#ac-8]]). This AC is
  also that the pass was **run** that way: the summary's per-site table gives, for every
  citation, the commit it was resolved at and how it was found (`-S` or the blame fallback).
  {#ac-3}
- **AC-4: every pin is rewritten and checked.** Each row of [[#baseline-pins]], and each pin R0
  found beyond it, has a row in the summary: the old text, the new text, the owner, the date,
  and one of the three outcomes of [[#r2]] item 4. No row is blank. {#ac-4}
- **AC-5: 26.5's site, 23.1's sites and 21.2's gold files** each have their record ([[#r3]],
  [[#r4]]). {#ac-5}
- **AC-6: the census fails on what it must fail on.** On fixture specs: a `cli.py:123` in a
  pending spec (fails); the same in a completed spec (passes); a
  `` `cli/grep_cmds.py::no_such_function` `` (fails); "walk every `src/refmatrix/*.py`" in a
  pending spec's AC (fails); an allow-list entry that matches nothing (fails); a
  `daemon.py:55` (passes, counted). {#ac-6}
- **AC-7: history is untouched.** `git diff --stat <base> <final>` touches no completed spec, no
  file under `workflow/implementation_summaries/`, `workflow/past_handoffs/`, `workflow/bullshit/`
  or `workflow/review-output/` other than this task's own logs. {#ac-7}
- **AC-8: nothing changed that was not a citation.** For every cite-only spec, the diff holds
  only lines the tool rewrote: the tool's `--check-diff` re-derives each changed line from its
  old text and fails on any other change. {#ac-8}
- **AC-9: the gates.** `./scripts/lint-gmd.sh` exits 0. [[task-29.1-registry-triage]]'s checker
  still exits 0 (a re-pointed spec keeps its id, so every `scheduled` target still resolves).
  {#ac-9}

## Test strategy {#test-strategy}

- **The tool is 29.5's, tested there**, including the rule that a citation is resolved at the
  commit that wrote its line. This task adds the tool's `--check`, `--check-diff` and
  `--verify-map` modes and the census test.
- **RED first.** `tests/test_spec_citation_census.py` is written with its fixture specs before
  the modes exist and is recorded failing. Then the modes. Then the pass over the real specs
  until the real-tree case is green: at the task's base that case is RED by 271 or more sites,
  which is the point.
- **Mutations** (each turns the census test RED; each is reverted in its own command):
  1. `--check` skips specs whose status is `approved`;
  2. `--check` does not resolve the symbol of a `::` citation;
  3. `--check` ignores `docs/`;
  4. the allow list tolerates an entry that matches nothing;
  5. `--check-diff` accepts any change on a line that contains a citation;
  6. `--verify-map` passes a row whose symbol is missing;
  7. the tool resolves a citation at the spec's last-change sha (AC-3's fixture writes `::g`);
  8. the tool does not compare a named symbol with the resolved def (AC-3's mismatch case is
     rewritten);
  9. the tool uses `git blame` on the line first (AC-3's reflow makes it write `::g`);
  10. the tool searches with `-S` (a substring): AC-3's `mod.py:10` beside `mod.py:100` row is
      resolved at two commits, so the test is red.
- **All output to files**, under `workflow/review-output/task-29.6/`.
{#test-strategy-list}

## Files {#files}

| File | Change |
|---|---|
| the not-completed specs under `workflow/plans/` that carry a hit (44 at `f3709d2`, more after the frozen branches merge) | [[#r1]], [[#r2]], [[#r3]] |
| `workflow/plans/task-t0-suite-trust-sweep.md`, if any T0 sub-task is still unbuilt | the same |
| the 21.2 gold files that name `cli.py` or `store.py` | [[#r4]], when the owner chooses to key on the definition |
| `docs/` (21 sites) | [[#r1]] |
| `tools/repoint_citations.py` | `--check`, `--check-diff`, `--verify-map` |
| `tools/split_maps/symbol_map.json`, `docs/architecture/module-split-map.md` | corrected rows, if [[#r0]] item 2 finds any |
| `tests/test_spec_citation_census.py`, `tests/fixtures/spec_citations/` | new |
| `tests/tiering.py` | `ALWAYS_FILES` gains the census test |
| `workflow/templates/task-spec.md`, `workflow/PLANNING_WORKFLOW.md` | [[#r8]] |
| `workflow/implementation_summaries/task-29.6-citation-and-pin-repoint.md` | new: the per-spec table, the pin table, the unresolved list |
{#files-table}

No file under `src/` changes. {#files-no-src}

## Out of scope {#out-of-scope}

- **Revising a requirement** beyond what a pin's rewrite needs. A spec that turns out to be
  wrong after the split goes back to its owner ([[#r3]]).
- **The per-track freshness revisions** the reviews schedule after 29.5 (one pass per track over
  T2 to T6). This task's diffs are an input to them, not a substitute.
- **History** ([[#r5]]).
- **Re-freezing 21.2's gold** ([[#r4]]).
- **Forbidding line citations of every module.** The census forbids them for the two modules
  that no longer exist as cited and counts the rest.
{#out-of-scope-list}

## Decisions taken in this spec {#decisions}

- **plan-29 D25: the pass also turns `daemon.py:N`, `verbs.py:N` and `mcp.py:N` into symbols.**
  - **Why:** they are stale already (the spec branches were cut 302 commits before `master`),
    the tool does it with no map, and T0's R0.1 would otherwise have every later task re-find
    the same sites by hand: **192** on `master` at `f3709d2` (128 + 55 + 9, in the not-completed
    specs, by the method [[#baseline-table]] states; 209 when the spec-branch copies are
    counted, which is the queue review's figure).
  - **Cost:** more specs in the diff. They are cite-only rewrites, one commit per track.
- **plan-29 D26: the census forbids dead file citations for good, and only counts the others.**
  - **Why:** a citation of `cli.py:N` can never be right again, so forbidding it costs nothing.
    Forbidding every `file:line` at once would fail on the history the census does not read
    and on habits the template has only just changed.
- **Not this spec's decisions:** that the pass is its own task and runs after 29.2 and 29.3
  (ruling L105); that a cite-only rewrite needs no re-approval and a location-bound one gets its
  owner's check (queue review `#p29-3`).
{#decisions-list}

## Revision note (2026-11-14, round 3: ch-bsd r2 and ruling L108) {#rev-note}

- **NS4:** a citation is resolved at the commit that first wrote it, and a named symbol is
  checked against the resolved def ([[#r1]], [[#ac-3]]). Round 4 (ch-bsd r3 `#m2`, ruling L110):
  that commit is the oldest one that added the exact token (`git log -S`), with `git blame` as
  the fallback only, because blame does not follow a reflow; AC-3 has a reflow fixture and a
  twice-added token; three mutations. After ch-bsd r4 (`#m2`, ruling L111): the search is
  `git log -G` with a digit boundary, not `-S`, which matches substrings; AC-3 has a row with
  `mod.py:10` beside `mod.py:100`, and a fourth mutation.
- **M8:** plan-29 D25's count is 192 on `master` at `f3709d2`, with the method stated; 209 is
  the queue review's count over the spec-branch copies ([[#baseline-table]], [[#decisions]]).
{#rev-note-list}
