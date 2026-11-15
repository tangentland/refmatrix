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
> Status: drafting (revision 1 after ch-bsd r1, ruling L139; fold table at [[#rev-r1]])
> Depends on: [[task-31.1-frontmatter-type-refusal]] merged first (both edit
> `ingest_gmd.py`). Order, fixed by ruling L139 ([[plan-of-plans#rulings]]): 31.3 → 31.4 →
> 31.1 → **31.6**, never two in flight; it needs 31.3's gate-tree helper and makes its
> upstream lint commit on top of 31.4's and 31.1's ([[#r7]]). Not on 29.5.
> Closes: bug-251 and bug-221 ([[bug_registry#registry]]); bug-257 is bug-221's duplicate.
> By ruling L136 it builds bug-185 R10's rule ([[#r5]]) and owns the one-time cleanup of the
> evidence-less edges in the dev store ([[#r10]]).
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
It never unlinks an old one. On the store copy (`rel_residue_census.py`, output
`workflow/review-output/spec31b-rel-residue-refmatrix.log`): 18 linkages carry `rel:`
evidence. Seventeen of them hold 8,628 edges, of which 136 have no evidence row. The
eighteenth is `part-of`, which the first draft left out (ch-bsd r1 S1): 16,357 edges, 15,898
with no evidence by design (heading containment, and organise's `subject_*` edges), 459 with
`rel:` evidence, and 14 `rel: part-of` edges on the same pair as a same-file containment
edge. {#fact-stale-edges}

| The 136 evidence-less edges on the 17 verbs, by shape (source → target) | Edges |
|---|---|
| GMD node → path-less concept named after a doc or memory | 76 |
| memory → path-less concept named after a doc or memory | 38 |
| **the misbinding's shape, total** | **114** (on 28 concepts; 18 are `reinforces`, 9 of them from a memory; 112 have the right twin: the same source and verb to the doc or memory the concept is named after) |
| GMD node → memory | 7 |
| path-less concept → doc | 7 |
| GMD node → path-less concept not named after a doc | 3 |
| memory → memory | 3 |
| memory → path-less concept not named after a doc | 2 |
{#fact-residue-table}

The 114 are what bug-216's re-bind left when 0.84.0's reingest moved its lines to the docs.
Re-binding the 62 lines here would leave 62 more, plus their root mirrors, without
[[#r5]]. {#fact-residue}

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

**The producer census runs first** (ch-bsd r1 S7). Before the RED for [[#r5]] is written,
R0 walks every `link` / `bulk_link` / `link_batch` caller in `src/` by bug-185 R10's two
conditions (its linkage can be a `rel:` verb; its concept side can be a GMD entity) and
classes each as writes-evidence, no-evidence-in-reach or no-evidence-unowned. The table
goes in the summary with path, symbol and sha. Two are known before the walk
([[#r5-producers]]). {#r0-census}

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
  not in the index: the lint does not resolve to it either. Built on the first miss of the
  exact lookup, once per `ingest_gmd_paths` call, so a batch whose links all resolve by `id`
  reads nothing extra. {#r4-index}
- **The index equals the disk corpus by construction** (ch-bsd r1 S2). A store row counts
  only when a file stands behind it: a `memory` row only when its `meta` carries
  `gmd_content_hash` (a bridged file has it; a `subject_*` row minted by organise and a
  `focus_*` row do not: 162 of 570 memory rows on the copy have no file); a `doc` row only
  when its `path` exists on disk (10 GMD doc rows on the copy point at files that are gone).
  So what the ingester resolves against is what [[#r8]]'s gate walks, and a row that exists
  only in the store can neither make a stem ambiguous nor take a link. {#r4-index-corpus}
- **The exact lookup is a doc or memory id, never a concept** (ch-bsd r1 M4). The order is:
  a doc or memory whose id is exactly the target; then the resolver's `project` and `stem`
  forms, with an ambiguous stem refused; and only when no doc is found by any form, today's
  fall-through. A path-less concept that carries the target's text as its name is reached
  only in that last step, so it cannot win over a doc or over a refusal. {#r4-order}
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
- **Producers with no evidence.** R10's producer rule comes with it, in full: the census
  ([[#r0-census]]); an evidence write added here to every **in-reach** producer (one whose
  code no other open plan or task owns), each with its test and mutation; the
  `UNOWNED_REL_PRODUCERS` list for the rest, each entry with a registry row; and
  `IngestStats.rel_unlink_skipped_unowned`, printed when non-zero. {#r5-producers}
- **The list has two entries at RED, not one** (ch-bsd r1 S7). R10 wrote "exactly one entry"
  and its AC-15 asserts that; the census at `f3a508f` already finds a second:
  | Producer | Writes | Stored sides (concept side, entity side) | Owner | Entry |
  |---|---|---|---|---|
  | `memory_link` (`daemon._op_memory_link`, the CLI's local path) | a caller-chosen linkage, no evidence | concept, memory | bug-218 | `("*", "concept", "memory", "bug-218")` |
  | `Store.link_part_of` (`store.py:3125`; callers `cli.py:1904`, `consolidate.py:798`, `daemon.py:5534`) | `part-of`, no evidence | memory (the subject), memory (the leaf) | plan-26's organisation, open and pre-mod | `("part-of", "memory", "memory", "bug-265")` |

  `part-of` is a `rel:` verb (3,087 `rel:` evidence rows) and a `subject_*` memory is a GMD
  entity, so `link_part_of` meets both census conditions; 15,898 `part-of` edges have no
  evidence on the copy. This task's assertion is that the shipped list **equals the census
  record's unowned rows**, two today; bug-185's AC-15 is amended by its owner to read the
  same. A third producer the walk finds is classed the same way and added before RED.
  {#r5-two-entries}
- **"Stated", on today's per-row pass 2.** R10 writes "steps 5-7's write set", which are
  step numbers of bug-185's bulk pass. On the pass this task edits, the write set of one doc
  is every key issued by: pass 1's `same_as` link; the `rel:` loop's `store.link` calls and
  their root mirrors; `link_batch` as flushed by `bulk_link` (the hierarchy's `part-of`,
  `imports`, the tag, title, alias, body-term and phrase mentions, `titles`, `aliases`,
  `lead`); and the body-link loop's `mentions`. `resolve_pending_refs` and `link_denotes`
  run after every doc of the batch and are not part of a doc's set; a key a pending row
  resolves is written with its evidence, so the support check keeps it. The set is
  **collected in memory as the pass issues the keys**, never read back from `entity_links`:
  inside `_sync_paths` `link()` is buffered by `deferred_links`, and a read would miss this
  doc's own writes. {#r5-stated-calls}
- **What R5 does on each route.** At `f3a508f` a doc with a relpath-named `doc` row (every
  doc that was ever synced) is purged whole by the guard before pass 2, on the sync route
  and on the code+docs route, so its old edges are already gone when R5 would run. That
  purge is bug-264, and 31.1 removes it before this task starts
  ([[task-31.1-frontmatter-type-refusal#r6]], ruling L144). At this task's base, then, no
  route purges a GMD doc's nodes on an edit, and **R5 does the work on every route**: sync,
  the code+docs pass, `ingest-gmd` and the bridge. R10's sync leg assumes "no relpath-named
  `doc` row", which a real sync never leaves; after 31.1 its conclusion holds for another
  reason, and that is a note for bug-185's owner. {#r5-routes}
- **The write.** Each unlink is the ordinary `Store.unlink`, logged, so a replay agrees. The
  batched `Store.bulk_unlink` is bug-185's, with the rest of its bulk path. {#r5-write}
- **"Stated" is every link write of the pass** (ch-bsd r1 S1; R10's own rule). The new write
  set is the `rel:` edges, the heading hierarchy's `part-of` edges, `imports`, mentions and
  every other link the pass writes for the doc. A pair the doc's own structure writes is
  never unlinked: deleting `rel: part-of -> [[#root]]` under a heading whose containment
  edge is that same pair keeps the edge (14 such pairs on the copy). R0's census names
  `part-of`'s two producers, the hierarchy and organise's `subject_*` edges. {#r5-stated}
- **Whose it is: ruled.** Ruling L136 (1): this task builds the rule, as one function on
  today's per-row pass 2, with R10's own acceptance legs ([[#ac-5]]). bug-185 later finds it
  built and changes only the write to `bulk_unlink`; a note goes into bug-185's spec at its
  build. bug-257 is closed as a duplicate of bug-221. {#r5-whose}

### R6: the corpus is fixed in the same change {#r6}

The docs commit that follows the code rewrites the links the new lint fails: the folded links
under `plan-31 D12` (a) (11 in 9 repo files; the 35 in memory files are the lead's edit, listed in
the summary) and any ambiguous link R0 finds. `./scripts/lint-gmd.sh` is 0 errors after it.
{#r6-body}

### R7: one upstream lint, three tasks {#r7}

The order is fixed by ruling L139: **31.4 → 31.1 → 31.6**, never two in flight, each upstream
commit on top of the previous, each re-vendor from the sha that holds the earlier ones.
{#r7-body}

- **31.4's change** (read from `task-31.4-retire-standing-warnings` on `spec-plan31a` at
  `3225a16`; L133 M8): an opt-in `--strict` flag (any warning makes the exit 1, the summary
  line ends `(strict: warnings fail)`), passed by `scripts/lint-gmd.sh`, and
  `session/recall-state` added to `KNOWN_MEMORY_TYPES`. This task's re-vendor keeps both.
  {#r7-31-4}
- **31.4's nine stem links.** 31.4 rewrites its nine `ambiguous-stem` links (`INDEX` ×3,
  `adr-template` ×6) to the full frontmatter id of the doc each sentence is about, while
  they still warn. A full id is an exact-id hit under [[#r1-table]], so this task inherits
  none of them. Had this task gone first, project-before-stem would have bound all nine
  without a warning, perhaps to the wrong `INDEX`; the order exists to prevent that
  (ch-bsd r1 S3). {#r7-nine}
- **`ambiguous-stem` leaves the warning classes.** Here it becomes an error ([[#r3]]), so it
  is no longer one of the classes `--strict` exists for. 31.4's
  `test_every_warn_class_has_a_must_fail_fixture` reads the list of warn classes: this task
  updates that list and moves the class's must-fail fixture to the error tests, in the same
  commit. {#r7-warn-class}
- **31.1's change.** The lint's error for a list-valued `id:` or `title:` (bug-255) is
  [[task-31.1-frontmatter-type-refusal#r3]]'s. `[ref-parity]` ([[#r8]]) is added beside
  31.1's `[frontmatter-parity]` in the same script. {#r7-31-1}
- **The gate file.** This task adds one line to `scripts/lint-gmd.sh`,
  `# gate-file: tools/gmd/resolve.py`, so 31.3's helper places the new module in every test
  tree ([[#tests-helper]]). {#r7-gate-file}

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
  When it runs is Q40's ([[plan-of-plans#questions]], open: one reingest window for 31.1,
  31.6 and 26.5, or one each); this spec needs only that [[#r10]] and [[#ac-9]] follow it in
  the same window. {#r9-reingest}
- **The recount is the proof**, on the dev store after that run ([[#ac-9]]). {#r9-recount}
- **Every other store is a separate user go**, per store. Until a store is re-derived its
  stem, project and folded links stay as they are today; nothing gets worse. The fleet's
  counts in [[#baseline-fleet-table]] are the size of what a re-derive would re-bind.
  {#r9-fleet}
- **Residue the reingest does not remove:** the 114 evidence-less edges of
  [[#fact-residue-table]]. They have no evidence row to attribute them to a file, so
  [[#r5]] cannot find them. [[#r10]] removes them. {#r9-residue}

### R10: the one-time cleanup of the misbinding's residue (ruling L136) {#r10}

Ruling L136 (3) gives the 114 edges to this task's store step: a one-time cleanup with a
manifest, in the same user-gated window as the reingest. {#r10-body}

- **The class.** An `entity_links` row is residue when all of these hold:
  1. no `linkage_evidence` row exists for its `(linkage, concept, entity)`;
  2. its linkage carries at least one `rel:` evidence row in the store, and is not `part-of`
     or another linkage the ingest writes without evidence ([[#fact-stale-edges]]);
  3. its target (the `entity_id` side) is a path-less concept whose name is the name of a
     `doc` or `memory` row of the same partition;
  4. its source (the `concept_id` side) is a doc, a memory, or a GMD node (a concept with a
     `path`);
  5. it matches no `UNOWNED_REL_PRODUCERS` signature ([[#r5-producers]]).
  {#r10-class}
- **Why that class and not all 136.** Conditions 3 and 4 are the shape only the misbinding
  made: a `rel:` line whose bare target bound a same-named concept instead of the doc. The
  other 22 evidence-less edges ([[#fact-residue-table]]) have other shapes and other
  possible writers (a hand `memory link` has no evidence row until bug-218); they are left
  alone and printed as counts by shape. {#r10-not-all}
- **After the reingest, never before.** The reingest gives every `rel:` line that is stated
  today its evidence row, so condition 1 then means "no line states this edge". Run before
  it, the cleanup would also take the 62 misbound edges whose evidence [[#r5]] is about to
  move. The op refuses to apply while the store's `gmd` derive stamp is older than this
  task's code, and says so. {#r10-order}
- **The op.** `rmx repair-index --rel-residue` (a verb, a daemon op and the CLI flag, beside
  `--entities` and `--fragments`). With `--dry-run` it prints the count of the class, the
  count that has the right twin, the `reinforces` count, and the other evidence-less edges
  by shape, and writes nothing. Without it: the manifest first, then one `Store.unlink` per
  edge (logged, so a replay agrees), then the `commit` record. {#r10-op}
- **The manifest** is `.refmatrix/removal/<id>.cleanup.jsonl`, one record per edge in 22.2
  R4's link form ([[task-22.2-repair-then-remove#r4]]): the linkage, both ends by partition,
  kind and name with their ids, the weight, the reason `rel-edge-without-evidence`, and the
  twin doc or memory when there is one. It is written and synced before the first unlink; if
  it cannot be written nothing is unlinked. {#r10-manifest}
- **The 18 `reinforces` edges** are in the class by the same rule. The 9 from a memory are
  the rows bug-218's reader fix would count beside the direct edge to the memory the concept
  `denotes`; removing them here removes the double count before that reader exists.
  {#r10-reinforces}
- **Every other store** has its own residue; the dry run counts it, and its cleanup rides
  that store's own reingest go. {#r10-fleet}

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
  ids `a/readme-one`, `b/readme-two`; a citer with `rel: … -> [[README]]`; and a path-less
  concept named `README` already in the store, which must not win over the refusal (ch-bsd
  r1 M4). The lint:
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
    and `rel_unlink_skipped_unowned` is 1; a second edge with the same linkage and concept
    side that differs **only in its entity-side kind**, so that its signature is not listed,
    is unlinked;
  - an edge another producer wrote with no evidence on a key no `rel:` line ever stated
    (`Store.link("part-of", <node>, <external concept>)`) is kept: the evidence-keyed rule
    never sees it (bug-185 AC-11's external-producer leg);
  - **the sync leg** ([[#r5-routes]]): the same re-target through the real `_sync_paths`, run
    twice so the relpath row exists, and the same through `as_memory=True`. After the edit
    the old edge is not in `entity_links`, the new one is, with one evidence row, and the
    anchors kept their ids (31.1's rule), so the unlink is R5's own doing on both routes;
  - **per in-reach producer** the census finds (bug-185 AC-14 (a)): run on a throwaway
    store, its edge has an evidence row naming the producer; if the census finds none
    in reach, the summary says so and this leg is the census record;
  - **the census record** (bug-185 AC-14 (c)): the summary's table lists every call site
    with its class; every unowned site has a registry row and a list entry; a unit test
    asserts each entry's bug id is a registry row whose status is not `fixed`;
  - **the list assertion** (bug-185 AC-15): the test first asserts the shipped
    `UNOWNED_REL_PRODUCERS` equals the census record's unowned rows ([[#r5-two-entries]]),
    then runs AC-15's two legs on it: a `(reinforces, memory, concept)` edge with its own
    non-`rel:` evidence survives by the evidence clause with `rel_unlink_skipped_unowned`
    0; a `(reinforces, concept, memory)` edge with no other evidence survives by the
    wildcard entry with the counter at 1;
  - a dropped `rel: part-of` line whose key the heading hierarchy writes again keeps its
    edge;
  - a doc whose `rel:` line is deleted loses that edge.

  These are [[task-bug185-bulk-gmd-ingest#ac-11]]'s bug-221 half and
  [[task-bug185-bulk-gmd-ingest#ac-14]] and [[task-bug185-bulk-gmd-ingest#ac-15]], run on the
  per-row path. **RED** at base (E line: the old edge is still there). {#ac-5}
- **AC-6: the parity census.** `check-gmd-parity`'s `[ref-parity]` on (i) the repo scope: 0
  findings; (ii) a fixture where a doc outside the lint scope takes the stem of a linted doc:
  one finding naming the link and both answers; (iii) on a throwaway store, a `memory` row
  with no `gmd_content_hash` (the shape of a `subject_*` row) and a `doc` row whose file is
  gone each take the stem of a linked doc: the ingest binds the link exactly as before, and
  reports no ambiguity (ch-bsd r1 S2). `tests/test_bug179_anchor_parity.py`'s sibling test
  calls the same function as the script. **RED** at base (E line: the function
  does not exist); the must-fail fixture is what proves the gate can fail
  ([[feedback_clean_corpus_hides_a_dead_gate]]). {#ac-6}
- **AC-7: one text.** The test reads `tools/gmd/resolve.py` and
  `src/refmatrix/gmd_resolve.py` and fails on any byte of difference; the summary records the
  upstream sha both were taken from. Upstream == vendored is gated too (ch-bsd r1 M3):
  `resolve.py` joins `lint.py` and `slice.py` in the parametrize of
  `tests/test_bug179_anchor_parity.py::test_ac8_vendored_tool_is_a_committed_upstream_blob`,
  so all three copies are checked by a test and none by hand. **RED** at base (the files do
  not exist). {#ac-7}
- **AC-8: the upstream gate test.** `scripts/test-lint-gates.py` in the upstream repo gains
  AC-2's and AC-3's cases and passes there; the re-vendored `tools/gmd/lint.py` and
  `tools/gmd/resolve.py` are byte-identical to the upstream files at the recorded sha, and
  31.1's `bad-frontmatter-type` cases still pass. **Gate.** {#ac-8}
- **AC-9: the recount, all three classes, by identity (rulings L132, L139; ch-bsd r1 M5).**
  Right after the dev store's forced reingest, with the dev tree at the reingest's sha:
  `resolver_landing.py` on a fresh copy classes **each of the lines the lint resolves by
  stem or project** (107 at base, listed by file and line in the R0 output) as
  `doc_or_memory` or `anchor_node`: none in `target_unresolved`, `other_concept` or `stale`
  (37, 62 and 8 at base). `scripts/check-rel-landing.py`'s totals are recorded beside it. A
  stale or unresolved line that is not one of those lines is listed and is not this task's:
  the tree moves (on the copy of 02:34 read against a later tree, `stale` was 340 and
  `target_unresolved` 355). The loss of inbound edges on every doc edit (bug-264) is fixed by
  31.1 before this task ([[task-31.1-frontmatter-type-refusal#r6]]), so it no longer undoes
  what the reingest binds. **Measurement**,
  on the live store's copy, after the user's go. {#ac-9}
- **AC-10: the repo is clean under the new lint.** `./scripts/lint-gmd.sh` exits 0 after
  [[#r6]]'s docs commit. Its precondition is the lead's edit of the 35 folded links in the
  memory dir, which the gate scans; the summary names the commit or the date of that edit.
  **Gate.** {#ac-10}
- **AC-12: the residue cleanup removes the class and nothing else.** A throwaway store
  seeded with one edge of each row of [[#fact-residue-table]] (written directly, with no
  evidence), one residue-shaped edge that **has** an evidence row, one evidence-less
  `part-of` edge, and one edge matching an `UNOWNED_REL_PRODUCERS` signature.
  `repair-index --rel-residue --dry-run` prints the class count 2 (node source, memory
  source) and the other shapes, and changes nothing. The apply unlinks exactly those two,
  logs an `unlink` for each, and leaves every other edge; the manifest holds two records by
  name and a `commit`; with the unlink made to fail after the write, the manifest has the
  records and no `commit` and both edges are still there; with `.refmatrix/removal`
  unwritable, nothing is unlinked; a rebuild from the log agrees; with a stale `gmd` derive
  stamp the apply refuses. **RED** at base (the flag does not exist). {#ac-12}
- **AC-13: the dev store's residue.** In the reingest window, after the reingest:
  the dry run's class count equals `rel_residue_census.py`'s on a copy taken just before
  (114 on the copy of 2026-11-15 02:34, 18 of them `reinforces`; the count is taken again
  then); after the apply the class count is 0, the manifest holds one record per edge, and
  the other shapes' counts are unchanged. **Measurement**, on the lead's run. {#ac-13}
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
| 8d | the unowned skip does not increment `rel_unlink_skipped_unowned` | AC-5's unowned leg (the count is 0) |
| 8e | a signature is matched on its linkage alone | AC-5's unowned leg (the second edge is kept) |
| 8f | ship `UNOWNED_REL_PRODUCERS` empty | AC-5's list assertion, and AC-15's second leg (unlinked, count 0) |
| 8g | "stated" is read back from `entity_links` | AC-5's sync leg (inside `deferred_links` the doc's own buffered writes are missed and its `part-of` edge is unlinked) |
| 8h | per in-reach producer: remove its evidence write | that producer's AC-5 leg |
| 8i | the rule is skipped when the pass runs under `_sync_paths` | AC-5's sync leg (the bridge leg stays green) |
| 9 | the ingest index takes lenient plain docs too | AC-3's variant with a plain `README.md` beside one GMD `README` (the link must bind the GMD doc) |
| 10 | edit one byte of `src/refmatrix/gmd_resolve.py` | AC-7, and `[ref-parity]`'s identity check |
| 11 | `[ref-parity]` resolves the ingest side against the lint's docs | AC-6 (ii) |
| 12 | swap the order to stem before project | AC-3's third-doc leg (ambiguous instead of resolved) |
| 13 | the ingest tries today's lookup (concept last) before the resolver | AC-3 (the `README` concept is bound) |
| 14 | the index takes every `memory` row, with or without `gmd_content_hash` | AC-6 (iii) |
| 15 | the index takes a `doc` row whose file is gone | AC-6 (iii) |
| 16 | the cleanup drops condition 3 (any evidence-less edge on a `rel:` verb) | AC-12 (the other shapes are unlinked) |
| 17 | the cleanup counts `part-of` as a `rel:` verb | AC-12 (the containment edge is unlinked) |
| 18 | the cleanup unlinks before it writes the manifest | AC-12's failing-unlink leg |
| 19 | the cleanup ignores the derive stamp | AC-12's last leg |
| 20 | drop the `# gate-file:` line for `resolve.py` | every test that builds a gate tree (the lint's import fails) |
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
`clear_rel_evidence`); `scripts/check-gmd-parity.py` (R8); `scripts/lint-gmd.sh` (one `# gate-file:` line);
the `repair-index --rel-residue` verb, daemon op and CLI flag (R10; `verbs.py`, `daemon.py`,
the `cli` module that holds `repair_index`, and the removal module for the selection);
`tests/test_bug179_anchor_parity.py` (the blob test's parametrize); each in-reach producer
site the census names (an evidence write; none is known before the walk); `docs/gmd/SPEC.md`; the docs commit
of [[#r6]]; new `tests/test_bug251_one_resolver.py`; `workflow/bug_registry.md` (bug-251, bug-221); the implementation summary. {#files-list}

## Risks {#risks}

- **The upstream file is shared.** 31.4, 31.1 and this task each change
  `~/claude_tools/gmd/lint.py`, in that fixed order ([[#r7]]); a re-vendor from a sha that
  lacks an earlier commit would drop a fix, the bug-068 shape. AC-7's blob test and AC-8 pin
  it. {#risk-upstream-order}
- **Three copies of one file.** The identity check is the only thing keeping them one text; it
  runs in the docs gate and in the suite. A change made in the package copy fails both. A
  change made upstream reaches this repo only at a re-vendor, as `lint.py` does. {#risk-copies}
- **Other repos' lints.** viascope runs the upstream lint: by the census it has no folded link
  and no link through an ambiguous stem, so nothing new fails there; its own lint scope was
  not measured, and the upstream commit is run against it before it lands. cliquedb (110
  folded links) and cliquet (3) fail only when they re-vendor; the migration guide lists the
  fix. A repo that vendors `lint.py` without `resolve.py` gets an `ImportError` at its next
  re-vendor (cliquedb, cliquet); the migration guide says the two files travel together
  (ch-bsd r1 M3). This task edits no other repo. {#risk-fleet-lint}
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
- **The cleanup removes edges nothing can re-derive.** A residue edge has no evidence, so
  nothing says which line made it. The class is narrow on purpose ([[#r10-not-all]]), the
  manifest holds every edge by name, and 112 of the 114 have the right edge beside them.
  The two without a twin are listed in the dry run for the lead to read before the apply.
  {#risk-r10}

## Out of scope {#out-of-scope}

- The 22 evidence-less edges outside [[#r10-class]], and any store's residue but the dev
  store's.
- Branch-aware lint, generated anchors, a before/after node check
  ([[plan-of-plans#post-mod]]).
- `imports:` resolution; cross-partition `rel:` binding; a doc id declared by two files in
  the ingest scope (the lint's `duplicate-doc-id` covers its own scope).
- Re-deriving any store but the dev store.
{#out-of-scope-list}

## Test trees {#tests-helper}

Every test here that needs the gate's scripts in a throwaway tree (AC-2, AC-3's lint side,
AC-6, AC-7) builds it with 31.3's shared helper, `tests/gmd_gate_tree.py`, which copies
exactly the files `scripts/lint-gmd.sh` declares on its `# gate-file:` lines and takes
per-file text overrides (`task-31.3-ledger-anchor-guard` `#r6` on `spec-plan31a` at
`3225a16`; rulings L133 B2 and L139). This task adds the one line
`# gate-file: tools/gmd/resolve.py` ([[#r7-gate-file]]) and no helper of its own: a fourth
hand-built tree would fail 31.3's bypass check. {#tests-helper-body}

## Revision 1: fold of ch-bsd r1 (ruling L139) and of L133, L136 {#rev-r1}

The review read `a4d245a`; R5 had already been rewritten as bug-185 R10's rule at `f2664e6`.

| Finding | Fold | Where |
|---|---|---|
| S7 (updated report) R5 is R10 in wording only | AC-14 (a) and (c), AC-15's list assertion, AC-11's sync and external-producer legs, and R10's two missing mutations are carried; `link_part_of` is a second unowned producer, so the list has two entries; "stated" is mapped onto the per-row calls and collected in memory; what R5 does on each route is stated | [[#r0-census]], [[#r5-producers]], [[#r5-two-entries]], [[#r5-stated-calls]], [[#r5-routes]], [[#ac-5]], mutations 8d-8i |
| L144: bug-264 is fixed in 31.1, before this task | R5 does the work on every route; the sync leg is RED for R5 itself; AC-9's note; bug-265 cited | [[#r5-routes]], [[#ac-5]], [[#ac-9]], [[#r5-two-entries]], mutations 8g, 8i |
| M10 (updated report) text after L136 and the queue | folded at `9637f17` | [[#r7]], [[#r5-whose]] |
| S1 R5 can unlink another producer's edge on a shared verb; `part-of` left out of the count | "stated" is every link write of the pass; a pair the doc's structure writes is never unlinked; the count is redone with `part-of`; R10's producer census | [[#r5-stated]], [[#r5-producers]], [[#ac-5]] (the `part-of` leg), mutations 8b, 8c, [[#fact-stale-edges]] |
| S2 `[ref-parity]` does not compare the corpus the ingester reads | the index counts a store row only when a file stands behind it | [[#r4-index-corpus]], [[#ac-6]] (iii), mutations 14, 15 |
| S3 no agreed order with 31.4; its nine links | 31.4 → 31.1 → 31.6; 31.4's change named; the nine are 31.4's, by intent; the warn-class list | header, [[#r7]] |
| M1 decisions and closures | D12 cited as decided (at `d788602`); closes bug-251 and bug-221, bug-257 a duplicate; bug-255 is 31.1's | header, [[#d12]] |
| M3 upstream == vendored not gated for `resolve.py` | joins the existing blob test; the `ImportError` risk | [[#ac-7]], [[#risk-fleet-lint]] |
| M4 the exact lookup could reach a concept first | the order is stated; a `README` concept in AC-3 | [[#r4-order]], [[#ac-3]], mutation 13 |
| M5 AC-9 needs a pinned tree and the 107 by identity | by identity, right after the reingest, at its sha; the memory-link edits as AC-10's precondition | [[#ac-9]], [[#ac-10]] |
| L133 M8 | 31.4's linter change named | [[#r7-31-4]] |
| L133 B2 | the shared helper and one `# gate-file:` line | [[#tests-helper]], [[#r7-gate-file]], mutation 20 |
| L136 (1) | this task builds R10's rule; bug-257 a duplicate of bug-221 | [[#r5-whose]], header |
| L136 (3) | the residue cleanup, with a class, a dry run, a manifest and two ACs | [[#r10]], [[#ac-12]], [[#ac-13]], mutations 16-19 |
{#rev-r1-table}

## Decisions {#decisions}

Decisions live in [[plan-of-plans#decisions]] and [[plan-of-plans#rulings]]; this section
cites them and records none of its own. {#decisions-rule}

- **`plan-31 D12`, decided** by ruling L125 on the recommendation (2026-11-15): case and
  `-` / `_` folding goes; the lint fails what it folded and names the exact id. Amended into
  [[#r1-fold]], [[#r3]], [[#r6]] and [[#ac-2]]. The cost is the measured one: 46 links here
  (11 in repo files, fixed in this task; 35 in memory files, the lead's edit), 110 in cliquedb
  and 3 in cliquet at their next re-vendor. The option not taken was folding as a fourth
  form on both sides. {#d12}
- **Ruling L136:** (1) this task builds bug-185 R10's rule ([[#r5-whose]]); (3) it owns the
  cleanup of the misbinding's residue ([[#r10]]). {#l136}
- **Ruling L139:** all of ch-bsd r1 folds ([[#rev-r1]]); the linter order ([[#r7]]). {#l139}
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
public name ([[#r4-public]]); the cleanup's class is the misbinding's shape, 114 of the 136
([[#r10-class]]), and the op is a `repair-index` flag ([[#r10-op]]). {#decisions-proposed}

**Registered from this spec's measurements:** bug-251's extent is 107 lines
([[#fact-107]]); bug-257 ([[#fact-stale-edges]]), closed as a duplicate of bug-221 by L136;
bug-255, taken by 31.1.
{#decisions-findings}
