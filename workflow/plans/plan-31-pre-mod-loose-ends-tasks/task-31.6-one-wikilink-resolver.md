---
gmd: "0.1"
id: task-31.6-one-wikilink-resolver
title: "Task 31.6: lint and ingest resolve a wikilink's doc through one resolver, so a link the gate passes is a link the graph holds (bug-251)"
tags: [task, plan-31, gmd, lint, ingest, wikilink, resolver, graph-correctness, bug-251]
metadata:
  node_type: task
  status: drafting
  plan: plan-31-pre-mod-loose-ends
  created: 2026-11-15
  updated: 2026-11-15
---

# Task 31.6: one wikilink resolver {#root}

> Plan: [[plan-31-pre-mod-loose-ends]] ([[plan-31-pre-mod-loose-ends#t6]]); admitted by the
> user, Q30 = a, 2026-11-15.
> Status: drafting (ch-architect on Fable, 2026-11-15; ch-bsd spec review next)
> Depends on: [[task-31.1-frontmatter-type-refusal]] merged first (both edit
> `ingest_gmd.py`). Not on 29.5: it touches `tools/gmd/`, `ingest_gmd.py`, two scripts and one
> method beside `clear_rel_evidence`.
> Closes: bug-251 ([[bug_registry#registry]]). [[#r5]] is the fix bug-185 R10 already
> specifies for bug-221, which bug-257 repeats; which task builds it is the lead's to rule
> ([[#r5-whose]]).
> Decision: `plan-31 D12`, decided in [[plan-of-plans#decisions]] ([[#d12]]).
> Base for every measurement here: `f3a508f`, and a copy of the dev store's read snapshot
> taken 2026-11-15 02:34.

rel: part-of -> [[plan-31-pre-mod-loose-ends]]
rel: implements -> [[plan-31-pre-mod-loose-ends#t6]]
rel: depends-on -> [[bug_registry#registry]]
rel: depends-on -> [[refmatrix/gmd-spec#references]]
rel: depends-on -> [[refmatrix/gmd-spec#project-namespace]]
rel: depends-on -> [[task-bug179-lint-ingest-anchor-parity]]
rel: derives-from -> [[task-bug216-rule-docs-in-graph]]
rel: depends-on -> [[orchestration#release]]
rel: depends-on -> [[plan-of-plans#decisions]]
rel: derives-from -> [[task-bug185-bulk-gmd-ingest#r10]]
rel: related-to -> [[task-bug218-reinforcement-edge-direction#r2b]]
rel: depends-on -> [[plan-31b-spec-census]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: reinforces -> [[feedback_converge_repeated_shapes]]
rel: related-to -> [[task-31.1-frontmatter-type-refusal]]

## Why {#why}

The lint decides whether a `[[doc#anchor]]` link is sound; the ingester decides what the graph
holds. They resolve the doc part by different rules. The lint accepts a frontmatter `id`, a
filename stem, an id with the project prefix left off, and an id folded for case and `-` / `_`.
The ingester binds the exact name only. A link the lint accepts by any form but the first
lands nowhere, or on a stray concept that happens to carry the same name. bug-251 counted 37
such lines; the count below is 107, because the other 70 do land, on the wrong entity.
This is the third time two parsers of one syntax have disagreed (bug-036, bug-179), and the
second for target resolution (bug-216). One resolver ends the class for the doc part of a
link, as bug-179's parity check ended it for anchors. {#why-body}

## Measured (2026-11-15) {#baseline}

Scripts and outputs: [[plan-31b-spec-census]]. Corpus reads use the lint scope of
`scripts/lint-gmd.sh` on the dev tree; store reads use a copy of `catalog.read.duckdb` opened
read-only. {#baseline-how}

### By which form the lint resolves each link {#baseline-forms}

`resolver_census.py` replays `lint.py`'s order (id, stem, project prefix, fold, fold with
prefix) for every cross-doc link of every GMD doc, and asks whether the ingester registers the
exact name. Output `workflow/review-output/spec31b-resolver-census-refmatrix.log` (745 files
plus 411 memory files, 1,153 GMD docs, 15,547 ingester names):

| Form the lint resolves by | `rel:` links: ingester binds / misses | body links: binds / misses |
|---|---|---|
| frontmatter `id` | 5,085 / 0 | 4,863 / 0 |
| filename stem | 0 / 82 | 0 / 55 |
| id without its project prefix | 0 / 19 | 0 / 19 |
| fold (case, `-` = `_`) | 0 / 12 | 0 / 34 |
| legacy `name:` used as the id | 0 docs | 0 docs |
| **lint resolves, ingester misses** | **113** (107 in repo files, 6 in memory files) | **108** |
{#baseline-forms-table}

Every link the lint resolves by `id` binds; every link it resolves by another form misses.
The two rules differ in exactly the forms, and in nothing else. {#fact-forms}

### Where the 107 repo `rel:` lines landed {#baseline-landing}

`resolver_landing.py` classes each of those lines with `scripts/check-rel-landing.py`'s own
rules, on the store copy. Output `workflow/review-output/spec31b-resolver-landing-refmatrix.log`:

| Class | Lines | By form | The recount of 2026-11-14 (`recount-0.84.0-refmatrix.log`) |
|---|---|---|---|
| `target_unresolved` (no edge, a pending row) | 37 | stem 31, fold 6 | `target_unresolved: 37`: all of it |
| `other_concept` (bound to a path-less concept that carries the link's text as its name) | 62 | stem 43, project 19 | `other_concept: 62`: all of it |
| `stale` (evidence, no live edge) | 8 | stem 8 | `stale: 8`: all of it |
{#baseline-landing-table}

- The three classes of the recount that are not "landed on a doc, a memory or an anchor" are
  bug-251, whole: 37 + 62 + 8 = 107 of 4,232 authored lines, in 47 files. {#fact-107}
- The 62 are a misbinding. `[[SYSTEM]]` finds no doc named `SYSTEM`, then the concept `SYSTEM`
  minted from a title or a body mention, and binds it (`_resolve_target_eid`'s last resort for
  a bare name). The recount's AC, `target_unresolved` 0, would pass with all 62 still wrong.
  {#fact-misbind}

### An edge outlives the line that made it {#baseline-stale-edges}

Re-ingesting a doc clears its `rel:` evidence (`clear_rel_evidence`) and writes the new edges.
It never unlinks an old one. On the store copy: 8,619 edges on the 17 `rel:` verbs; 136 have
no evidence row; 114 of those point at a path-less concept named after an ingested doc or
memory (28 concepts). Those are what bug-216's re-bind left when 0.84.0's reingest moved its
lines to the docs. Re-binding the 62 lines here would leave 62 more, plus their root
mirrors. {#fact-stale-edges}

### The two corpora {#baseline-corpora}

`corpus_diff.py`, output `workflow/review-output/spec31b-corpus-diff-refmatrix.log`. The lint
sees its scope; the store holds every authored GMD doc the ingest walk includes.

| Measure | Value |
|---|---|
| GMD docs in the lint scope / authored GMD docs in the ingest scope | 1,168 / 1,204 |
| in the ingest scope only | 36 (`tests/` 33, `SETUP.md`, `handoff.md`, the memory index) |
| ids or stems unique for the lint and shared in the ingest scope | 0 / 0 |
| links where the stem form and the project form both hit | 106; a different doc by the two orders: 0 |
| stems several lint docs share / not also an id / links resolved only through one | 61 / 4 / 0 |
{#baseline-corpora-table}

The corpora agree today. Nothing keeps them agreeing: a fixture under `tests/` that takes the
stem of a doc would make a stem unique for the lint and shared in the store. {#fact-corpora}

### The fleet {#baseline-fleet}

`resolver_census.py` over each roster repo's root and memory dir
(`workflow/review-output/spec31b-resolver-census-fleet.log`). The scope is the whole root, not
each repo's own lint scope, so vendored and duplicated trees are counted: an upper bound, used
for proportions only.

| Repo | `rel:` links by stem / project / fold | body links by stem / project / fold |
|---|---|---|
| cliquedb | 2,699 / 0 / 92 | 5,128 / 0 / 18 |
| viascope | 8 / 0 / 0 | 0 / 0 / 0 |
| orderly | 23 / 7 / 0 | 24 / 4 / 0 |
| cliquet | 97 / 8 / 2 | 2,129 / 280 / 1 |
| atldb | 16 / 4 / 0 | 0 / 5 / 0 |
| atlftpd | 16 / 4 / 0 | 0 / 5 / 0 |
| thiquet | 592 / 55 / 0 | 1,027 / 76 / 0 |
{#baseline-fleet-table}

- Stem and project links are the fleet's normal way to write a link: thousands depend on
  them. Both are in the GMD spec ([[refmatrix/gmd-spec#references]],
  [[refmatrix/gmd-spec#project-namespace]]). {#fact-fleet-stem}
- Folded links are few: 46 here (12 `rel:`, 34 body; 11 in 9 repo files, 35 in memory files),
  110 in cliquedb, 3 in cliquet, none elsewhere. Folding is not in the GMD spec. {#fact-fleet-fold}
- No doc in the eight repos or the 20 non-empty memory dirs is keyed by a legacy `name:`.
  {#fact-name-alias}

### The tooling is upstream {#baseline-upstream}

`tools/gmd/lint.py` is a byte-identical vendored copy of `~/claude_tools/gmd/lint.py`, its own
repo ([[task-bug179-lint-ingest-anchor-parity#f-canonical]]). viascope runs the upstream lint;
cliquedb and cliquet vendor it. A lint change lands upstream first and is re-vendored
([[task-bug179-lint-ingest-anchor-parity#d4]]). The upstream lint is a stdlib-only script; the
ingester is a package module. Neither can import the other. {#fact-upstream}

## Requirements {#requirements}

### R0: re-measure at base {#r0}

Run the four census scripts at the task's base and record the outputs. The landing recount
needs a fresh read-only copy of the dev store's snapshot. If [[#baseline-corpora-table]]'s two
zero rows are no longer zero, the links behind them are listed in the summary and fixed in the
docs commit of [[#r6]]. {#r0-body}

### R1: the rule {#r1}

A link's doc part `T`, written in a doc whose project is `P`, resolves against a set of GMD
docs, each with a frontmatter `id` (or, without one, the id its parser gives it) and a
filename stem. The first form that hits wins:

| # | Form | Hits when | Source |
|---|---|---|---|
| 1 | `id` | a doc's id is exactly `T` | [[refmatrix/gmd-spec#references]] |
| 2 | `project` | a doc's id is exactly `P/T` | [[refmatrix/gmd-spec#project-namespace]] |
| 3 | `stem` | exactly one doc's filename stem is `T` | [[refmatrix/gmd-spec#references]] |
{#r1-table}

- **Ambiguous.** `T` matches no id and no `P/T`, and is the stem of two or more docs: the
  link is **refused**, with the candidates named. The spec's own words: a link "that resolves
  only by matching a filename stem shared by several docs is ambiguous". Today the lint warns
  and binds whichever doc it read first. {#r1-ambiguous}
- **Order.** Project before stem, where the lint has stem before project. It makes the
  ambiguity rule match the spec's "only", and no link changes its target: 106 links hit both
  forms and all 106 reach the same doc ([[#baseline-corpora-table]]). {#r1-order}
- **Not a form: folding** (`plan-31 D12`, decided: [[#d12]]). Matching is exact, case included.
  A link that resolves today only by folding becomes `dangling-doc`, and the message names
  the exact id it would have folded to. {#r1-fold}
- **Not a form: `name:`.** A doc with no `id:` is keyed by what its parser gives it (the
  stem), on both sides. No doc is keyed by `name:` today ([[#fact-name-alias]]). {#r1-name}
- **Unchanged.** Same-doc links (`[[#anchor]]`), the anchor part, `imports:`, and the ADR
  slash alias in the ingester. {#r1-unchanged}

### R2: one text {#r2}

The rule lives in one stdlib-only module, `resolve.py`, in the upstream gmd repo:
`project_name` and `load_config` (moved from `lint.py`), an index built from
`(doc id, path)` pairs, and `resolve_doc(index, target, project)` returning the doc id, the
form, or the ambiguous candidates. {#r2-body}

- Vendored byte-identical at `tools/gmd/resolve.py`, beside `lint.py`, re-vendored from the
  pinned upstream sha as bug-179 did ([[task-bug179-lint-ingest-anchor-parity#r6]]). {#r2-vendor}
- Copied byte-identical to `src/refmatrix/gmd_resolve.py`, because the package cannot import
  from `tools/` and the upstream script cannot import the package ([[#fact-upstream]]). The
  copy carries no local edit; `scripts/check-gmd-parity.py` fails when the two files differ,
  and a test asserts the same ([[#ac-7]]). {#r2-copy}
- `lint.py` imports its sibling `resolve`. It is run as a script and loaded by path
  (`check-gmd-parity.py`, the tests), so it puts its own directory on `sys.path` before the
  import. `lint.resolve_refs` keeps its signature; `_norm_id` and the stem `setdefault` in
  `main` go. {#r2-lint}

### R3: the lint side {#r3}

`resolve_refs` asks the resolver. Issues: `dangling-doc` (no form hits), with a
"did you mean `<id>`" when a fold of `T` would have hit; `ambiguous-stem`, now at the
severity of `dangling-doc` (an error when a directory is in scope, a warning for a single
file), naming the candidates; `dangling-anchor` unchanged. {#r3-body}

### R4: the ingest side {#r4}

Before a target is looked up, its doc part is replaced by the id the resolver returns. One
function in `ingest_gmd.py` does it, and three sites call it: the `rel:` loop and the body
link loop of pass 2, and `resolve_pending_refs`. {#r4-body}

- **A public name.** The function is `ingest_gmd.resolve_link_target(store, ref, *, project,
  batch=None)`: the entity the ingester would bind for a link written as `ref` in a doc of
  that project, or the ambiguous candidates, or nothing. It is not underscore-private, so a
  reader that must find "what the ingester bound for this name" calls it instead of
  repeating the order. bug-218's `reinforcement.resolve_targets`
  ([[task-bug218-reinforcement-edge-direction#r2b]]) is the first such reader (asked for by
  its freshness revision); this task does not edit it. {#r4-public}

- **The index.** This call's parsed docs, plus the authored GMD docs and memories the store
  already holds in the active partition: `doc` rows whose `meta.gmd_version` is set and is
  not `lenient`, and `memory` rows. A row's stem is its `path`'s stem; a memory row has no
  `path`, and its name is its stem (the memory-file rule). Plain markdown read leniently is
  not in the index: the lint does not resolve to it either. Built on the first miss of an
  exact lookup, once per `ingest_gmd_paths` call, so a batch whose links all resolve by `id`
  reads nothing extra. {#r4-index}
- **The project** is `resolve.project_name` of the citing file: the same function, so the same
  answer, as the lint's. {#r4-project}
- **A hit by `project` or `stem`** rewrites the target name (`<id>` or `<id>#<anchor>`), and
  `_resolve_target_eid` then binds as today. The evidence `detail` keeps the link as written.
  {#r4-hit}
- **No hit** falls through to today's lookup unchanged, including the bare-name concept as
  the last resort and the pending row for a `rel:` line. {#r4-miss}
- **Ambiguous** binds nothing and is never pending: it is counted on `IngestStats`, named in
  the report (file, line, link, candidates), and reported on the code+docs and sync routes
  through [[task-31.1-frontmatter-type-refusal#r2]]'s channel. The gate refuses it first; this
  is for a corpus that no lint guards. {#r4-ambiguous}
- **A pending row** stores the link as written. `resolve_pending_refs` resolves it with the
  project of the row's `file`. {#r4-pending}

### R5: re-binding replaces the edge (bug-185 R10's rule) {#r5}

Re-binding must replace the old edge, not add a second one beside it: the 62 misbound lines
would otherwise each keep their edge to the path-less concept ([[#fact-stale-edges]]).
Ruling L132 keeps this requirement. {#r5-body}

- **The rule already has a spec.** [[task-bug185-bulk-gmd-ingest#r10]] (approved, on
  `master`, queue step 13) specifies exactly this for bug-221, which bug-257 repeats. This
  task runs at step 5 and its own store event needs the rule. So R5 **is** R10's rule, taken
  whole, and no second rule is written here. Where this section is shorter than R10, R10's
  text governs. {#r5-same}
- **Which edges.** The `(verb, source, target)` keys of the `rel:` evidence rows the clear
  removes for the file: the doc's direct lines, its root-mirror rows, and the rows its
  pending refs resolved. Keyed by evidence, never by "every edge whose source is a node of
  this doc". {#r5-keys}
- **When one is unlinked.** After the doc's whole new write set is in, an old key is
  unlinked only when both hold: the new write set does not state it; and **no
  `linkage_evidence` row supports it**, whichever file or producer wrote that row, and
  whether or not the row has a file and a line. bug-218 R1's `memory link:` evidence row
  has neither, on the same key as a memory's `rel:` line; it must count, or a user's hand
  link is unlinked when the GMD line is dropped
  ([[task-bug218-reinforcement-edge-direction#ac-11]]). {#r5-support}
- **Producers with no evidence.** R10's producer rule comes with it: the census of other
  producers of a `rel:`-verb edge, the `UNOWNED_REL_PRODUCERS` list with its one shipped
  entry for `memory_link` (owned by bug-218), and `IngestStats.rel_unlink_skipped_unowned`,
  printed when non-zero. Without it, `memory_link`'s evidence-less edge of today would be
  unlinked as stale. {#r5-producers}
- **The write.** Each unlink is the ordinary `Store.unlink`, logged, so a replay agrees. The
  batched `Store.bulk_unlink` is bug-185's, with the rest of its bulk path. {#r5-write}
- **Whose it is: for the lead.** Proposed: this task builds the rule as one function on
  today's per-row pass 2, with R10's own acceptance legs ([[#ac-5]]); bug-185 then finds it
  built and changes only the write to `bulk_unlink`; bug-185's spec says so in a note by its
  owner; bug-257 is closed as a duplicate of bug-221. The other way round (31.6 waits for
  bug-185) leaves the 62 edges in place after this task's reingest. Neither spec says which
  today. {#r5-whose}

### R6: the corpus is fixed in the same change {#r6}

The docs commit that follows the code rewrites the links the new lint fails: the folded links
under `plan-31 D12` (a) (11 in 9 repo files; the 35 in memory files are the lead's edit, listed in
the summary) and any ambiguous link R0 finds. `./scripts/lint-gmd.sh` is 0 errors after it.
{#r6-body}

### R7: one upstream lint, three tasks {#r7}

The lint's error for a list-valued `id:` or `title:` (bug-255) is
[[task-31.1-frontmatter-type-refusal#r3]]'s, not this task's; 31.1 lands first. This task's
upstream commit is made on top of 31.1's (and 31.4's, if it has landed), and the re-vendor
takes all of them. `[ref-parity]` ([[#r8]]) is added beside 31.1's `[frontmatter-parity]`
in the same script. {#r7-body}

### R8: the gate compares the two corpora {#r8}

`scripts/check-gmd-parity.py` gains a third check, `[ref-parity]`, run by
`scripts/lint-gmd.sh` over the same scope. For every cross-doc link of every linted GMD doc
it resolves the doc part twice with the one resolver: against the lint's docs, and against
every authored GMD doc the ingest walk includes under the project root plus the memory dirs
(disk only; no store). The two answers must be the same doc. A difference is an error naming
the file, the line, the link and both answers. It also fails when `tools/gmd/resolve.py` and
`src/refmatrix/gmd_resolve.py` differ. {#r8-body}

### R9: the stores {#r9}

The code changes no row by itself: an unchanged doc is skipped by its content hash, so its
links stay bound as they are. {#r9-body}

- **Re-binding needs every citing doc re-processed.** The existing tool is
  `rmx reingest --force --no-sessions` (it clears the stamps; it purges nothing). On the dev
  store that run took about 63 minutes at 0.84.0 (bug-252). It is a store event of the
  release: backups first, announced, its own user go ([[orchestration#release]] step 4).
  {#r9-reingest}
- **The recount is the proof**, on the dev store after that run ([[#ac-9]]). {#r9-recount}
- **Every other store is a separate user go**, per store. Until a store is re-derived its
  stem, project and folded links stay as they are today; nothing gets worse. The fleet's
  counts in [[#baseline-fleet-table]] are the size of what a re-derive would re-bind.
  {#r9-fleet}
- **Residue the reingest does not remove:** the 114 evidence-less edges of
  [[#fact-stale-edges]]. They have no evidence row to attribute them to a file, so R5 cannot
  find them; bug-185 R10 puts the same class out of its scope, with plan-22's dangling
  classes. Counted before and after in the summary; their removal is not this task
  ([[#out-of-scope]]) and has no owner today. bug-218's freshness revision measured that 9
  of the 114 are `reinforces` rows that its reader fix would count twice, and has asked the
  lead for an owner. {#r9-residue}

## Acceptance criteria {#acceptance}

New tests live in `tests/test_bug251_one_resolver.py` unless said otherwise.

- **AC-1: the three real shapes bind the doc.** On a throwaway store, three docs shaped like
  the live ones: file `CLAUDE.md` with `id: claude`; a doc with `id: proj/system_design_review`
  and that stem, under a `.gmd/config.yml` with `project: proj` (the fixture root holds a
  `.git` entry: `project_name` finds the root by it); a doc with
  `id: bug_registry`. A citer with `rel:` lines to `[[CLAUDE#a]]`, `[[system_design_review]]`
  and `[[bug_registry#registry]]`, and a path-less concept named `CLAUDE` already in the
  store. After `ingest_gmd_paths`: each line has one evidence row joined to a live edge whose
  target is the doc's anchor node or the doc row, never the concept; `stats.unresolved` is
  empty. **RED** at base (E lines: `[[CLAUDE#a]]` unresolved; the bare links bound to the
  concept or unresolved). {#ac-1}
- **AC-2: the same three through the gate.** The lint on that tree: 0 errors. And
  `[[bug-registry#registry]]` (the folded form): `dangling-doc` naming `bug_registry`, exit 1.
  **RED** at base for the folded link (E line: lint exits 0); **characterization** for the
  three. {#ac-2}
- **AC-3: an ambiguous stem is refused on both sides.** Two docs with the stem `README` and
  ids `a/readme-one`, `b/readme-two`; a citer with `rel: … -> [[README]]`. The lint:
  `ambiguous-stem` error naming both, exit 1. The ingest: no edge, no pending row, the link
  in the report with both candidates. With a third doc whose id is `<project>/README`, the
  link resolves to it on both sides. **RED** at base (E lines: lint exits 0 with a warning;
  the ingest binds or leaves a pending row). {#ac-3}
- **AC-4: a late target.** The citer is ingested before its stem-addressed target exists;
  the target is ingested in a later call; the pending row resolves to the doc. **RED** at
  base (E line: the row stays pending). {#ac-4}
- **AC-5: re-binding replaces, by bug-185 R10's legs.** A store holding the misbinding (the
  citer's line bound to the path-less concept; built in the test by writing that edge and its
  evidence row). The citer is re-processed:
  - the edge to the doc exists, the edge to the concept is gone, and an `unlink` event for it
    is in `facts.log`; a rebuild from the log agrees;
  - a second citer whose own `rel:` evidence supports the same edge keeps it;
  - an evidence row on the same key with **no file and no line** (the shape of bug-218 R1's
    `memory link:` row, written by the test) keeps the edge;
  - an edge matching a listed `UNOWNED_REL_PRODUCERS` signature, with no evidence, is kept
    and `rel_unlink_skipped_unowned` is 1; the same edge with an unlisted signature is
    unlinked;
  - a dropped `rel: part-of` line whose key the heading hierarchy writes again keeps its
    edge;
  - a doc whose `rel:` line is deleted loses that edge.

  These are [[task-bug185-bulk-gmd-ingest#ac-11]]'s bug-221 half and
  [[task-bug185-bulk-gmd-ingest#ac-14]] and [[task-bug185-bulk-gmd-ingest#ac-15]], run on the
  per-row path. **RED** at base (E line: the old edge is still there). {#ac-5}
- **AC-6: the parity census.** `check-gmd-parity`'s `[ref-parity]` on (i) the repo scope: 0
  findings; (ii) a fixture where a doc outside the lint scope takes the stem of a linted doc:
  one finding naming the link and both answers. `tests/test_bug179_anchor_parity.py`'s
  sibling test calls the same function as the script. **RED** at base (E line: the function
  does not exist); the must-fail fixture is what proves the gate can fail
  ([[feedback_clean_corpus_hides_a_dead_gate]]). {#ac-6}
- **AC-7: one text.** The test reads `tools/gmd/resolve.py` and
  `src/refmatrix/gmd_resolve.py` and fails on any byte of difference; the summary records the
  upstream sha both were taken from and `diff` against the upstream file. **RED** at base
  (the files do not exist). {#ac-7}
- **AC-8: the upstream gate test.** `scripts/test-lint-gates.py` in the upstream repo gains
  AC-2's and AC-3's cases and passes there; the re-vendored `tools/gmd/lint.py` and
  `tools/gmd/resolve.py` are byte-identical to the upstream files at the recorded sha, and
  31.1's `bad-frontmatter-type` cases still pass. **Gate.** {#ac-8}
- **AC-9: the recount, all three classes (ruling L132).** After the dev store's forced reingest, `scripts/check-rel-landing.py`
  over the lint scope: `target_unresolved` 0, `other_concept` 0 and `stale` 0 (37, 62 and 8
  at base), and `resolver_landing.py` on a fresh copy classes every line the lint resolves
  by stem or project as `doc_or_memory` or `anchor_node`. **Measurement**, on the live
  store's copy, after the user's go. If a line stays in `other_concept` whose target the
  lint does not resolve to a doc, it is listed and is not this task's. {#ac-9}
- **AC-10: the repo is clean under the new lint.** `./scripts/lint-gmd.sh` exits 0 after
  [[#r6]]'s docs commit. **Gate.** {#ac-10}
- **AC-11: no extra read when ids resolve.** A batch whose links all resolve by `id` runs no
  index query (asserted by counting the statement, or by a store double that fails on it).
  **RED** only if the index is built eagerly; written as a guard. {#ac-11}

## Must-fail mutations {#mutations}

| # | Mutation | Must turn RED |
|---|---|---|
| 1 | drop the `stem` form from `resolve_doc` | AC-1 (`CLAUDE`, `system_design_review` by stem), AC-4 |
| 2 | drop the `project` form | AC-3's third-doc leg, and a project-only link added to AC-1 |
| 3 | put folding back | AC-2's folded link |
| 4 | bind the first candidate of an ambiguous stem | AC-3 (both sides) |
| 5 | the body-link loop skips the resolver | AC-1's body-link leg |
| 6 | `resolve_pending_refs` skips the resolver | AC-4 |
| 7 | drop R5's unlink | AC-5 |
| 8 | R5 unlinks without checking other evidence | AC-5's second citer |
| 8a | the support check counts only evidence rows that have a file | AC-5's no-file leg |
| 8b | the unowned-signature check removed | AC-5's unowned leg (the listed edge is unlinked) |
| 8c | "stated" ignores the hierarchy's writes | AC-5's `part-of` leg |
| 9 | the ingest index takes lenient plain docs too | AC-3's variant with a plain `README.md` beside one GMD `README` (the link must bind the GMD doc) |
| 10 | edit one byte of `src/refmatrix/gmd_resolve.py` | AC-7, and `[ref-parity]`'s identity check |
| 11 | `[ref-parity]` resolves the ingest side against the lint's docs | AC-6 (ii) |
| 12 | swap the order to stem before project | AC-3's third-doc leg (ambiguous instead of resolved) |
{#mutations-table}

## Caller census {#census}

| Site | Today | After |
|---|---|---|
| `ingest_gmd.py` pass 2, `rel:` loop (`_target_name` → `_resolve_ref`) | exact name | resolver, then exact |
| `ingest_gmd.py` pass 2, body links | exact name | resolver, then exact |
| `ingest_gmd.resolve_pending_refs` | exact stored name | resolver on the stored link |
| `ingest_gmd.py` `imports:` loop | exact, batch only | unchanged |
| `lint.resolve_refs` (one caller, `lint.main`) | five forms | the resolver |
| `lint.project_name`, `lint.load_config` | defined in `lint.py`; read by `check-gmd-parity.py` (`load_config`, `_repo_root`) and the census scripts | defined in `resolve.py`, re-exported by `lint.py` under the same names |
| `scripts/check-rel-landing.py` | counts landing by evidence | unchanged; reads the recount |
| `scripts/check-gmd-parity.py` | anchors, scope | plus `[ref-parity]` and the identity check |
| `Store.clear_rel_evidence` (one caller, pass 2) | deletes evidence | unchanged; R5 reads the rows first |
{#census-table}

Other readers of a link's doc part, checked and unchanged: `rmx context` / `resolve_entity`
(names, not links), `brief.py`'s own `parse_gmd` (a different function), `tools/gmd/slice.py`
and `audit.py` (they do not resolve cross-doc targets against a corpus; R0 confirms by grep
and says so). {#census-other}

## Files {#files}

Upstream repo `~/claude_tools/gmd/` (first): new `resolve.py`; `lint.py`;
`scripts/test-lint-gates.py`; `SPEC.md` (§4: the three forms, their order, the ambiguity rule,
no folding); `gmd-migration-guide.md` (folded links, ambiguous stems, per repo).

This repo: `tools/gmd/lint.py` and `tools/gmd/resolve.py` (re-vendored);
`src/refmatrix/gmd_resolve.py` (the copy); `src/refmatrix/ingest_gmd.py` (R4, R5);
`src/refmatrix/store.py` or, after 29.5, `store_links.py` (one read beside
`clear_rel_evidence`); `scripts/check-gmd-parity.py` (R8); `docs/gmd/SPEC.md`; the docs commit
of [[#r6]]; new `tests/test_bug251_one_resolver.py`; `workflow/bug_registry.md` (bug-251; bug-221 and
bug-257 by the lead's ruling on [[#r5-whose]]); the implementation summary. {#files-list}

## Risks {#risks}

- **The upstream file is shared.** 31.1, 31.4 and this task each change
  `~/claude_tools/gmd/lint.py`. They land in the plan's order and each re-vendor is taken
  from the sha that holds the earlier ones; a re-vendor from an older sha would drop a fix,
  the bug-068 shape. AC-8 pins it. {#risk-upstream-order}
- **Three copies of one file.** The identity check is the only thing keeping them one text; it
  runs in the docs gate and in the suite. A change made in the package copy fails both. A
  change made upstream reaches this repo only at a re-vendor, as `lint.py` does. {#risk-copies}
- **Other repos' lints.** viascope runs the upstream lint: by the census it has no folded link
  and no link through an ambiguous stem, so nothing new fails there; its own lint scope was
  not measured, and the upstream commit is run against it before it lands. cliquedb (110
  folded links) and cliquet (3) fail only when they re-vendor; the migration guide lists the
  fix. This task edits no other repo. {#risk-fleet-lint}
- **The reingest is long** (63 minutes here, bug-252 unexplained) and holds the store busy.
  If bug-252's cause is found first, it runs faster; this task does not wait for it. {#risk-reingest}
- **The index read on a miss.** A single-file sync whose doc has one link that is not an id
  pays one query over the partition's docs and memories. R0 times it on the store copy and
  the summary states it; the band is under 100 ms, and over it the index is cached on the
  store per derive stamp instead. {#risk-index}
- **Cross-partition targets** are looked up in the active partition only, as today. A link
  from a project doc to a memory in another partition is not made better or worse.
  {#risk-partition}
- **R5 removes edges.** It removes only an edge that this doc's own cleared `rel:` evidence
  named, that the new text does not state, and that no evidence row of any kind supports;
  each unlink is logged. An edge another producer wrote on the same key with no evidence row
  is what R10's census and unowned list exist for ([[#r5-producers]]). {#risk-r5}
- **One rule in two specs.** Until the lead rules ([[#r5-whose]]), bug-185 R10 and this R5
  both claim the build. If both were built separately the unlink would run twice per doc and
  the two could drift. {#risk-r5-twice}

## Out of scope {#out-of-scope}

- Removing the 114 evidence-less edges already in the dev store, and their like elsewhere.
- Branch-aware lint, generated anchors, a before/after node check
  ([[plan-of-plans#post-mod]]).
- `imports:` resolution; cross-partition `rel:` binding; a doc id declared by two files in
  the ingest scope (the lint's `duplicate-doc-id` covers its own scope).
- Re-deriving any store but the dev store.
{#out-of-scope-list}

## Decisions {#decisions}

Decisions live in [[plan-of-plans#decisions]] and [[plan-of-plans#rulings]]; this section
cites them and records none of its own. {#decisions-rule}

- **`plan-31 D12`, decided** by ruling L125 on the recommendation (2026-11-15): case and
  `-` / `_` folding goes; the lint fails what it folded and names the exact id. Amended into
  [[#r1-fold]], [[#r3]], [[#r6]] and [[#ac-2]]. The cost is the measured one: 46 links here
  (11 in repo files, fixed in this task; 35 in memory files, the lead's edit), 110 in cliquedb
  and 3 in cliquet at their next re-vendor. The option not taken was folding as a fourth
  form on both sides. {#d12}
- **Ruling L132:** [[#r5]] stays; the recount AC is all three classes at 0
  ([[#ac-9]]); 31.1 lands before this task; the re-bind reingest of each store is its own
  user go ([[#r9]], and L125: a decision that changes a store on disk goes to the user).
  {#l132}

**Design proposed by this spec, for review** (not ledger decisions): the three forms and
their order ([[#r1-table]], [[#r1-order]]); an ambiguous stem is refused as an error on both
sides, never bound and never pending ([[#r1-ambiguous]], [[#r4-ambiguous]]); `name:` is not
an id source ([[#r1-name]]); one text in three files, held together by an identity check,
with upstream first ([[#r2]]); the ingest index holds authored GMD docs and memories only
([[#r4-index]]); the gate compares the two corpora ([[#r8]]); the resolver's ingest-side function has a
public name ([[#r4-public]]); R5 is bug-185 R10's rule, built here first ([[#r5-whose]]).
{#decisions-proposed}

**Registered from this spec's measurements:** bug-251's extent is 107 lines
([[#fact-107]]); bug-257 ([[#fact-stale-edges]]), which repeats bug-221, already owned by
bug-185 R10 ([[#r5-whose]]); bug-255, taken by 31.1.
{#decisions-findings}
