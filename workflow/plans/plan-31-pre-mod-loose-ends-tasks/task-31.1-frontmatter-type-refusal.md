---
gmd: "0.1"
id: task-31.1-frontmatter-type-refusal
title: "Task 31.1: a non-string frontmatter id or title is refused per file by lint and ingest alike, named on every route, and no longer fails the GMD batch (bug-244, bug-255, bug-258)"
tags: [task, plan-31, gmd, ingest, sync, bridge, lint, parity, frontmatter, batch-failure, bug-244, bug-255, bug-258, bug-264, bug-206]
metadata:
  node_type: task
  status: drafting
  plan: plan-31-pre-mod-loose-ends
  created: 2026-11-15
  updated: 2026-11-15
---

# Task 31.1: frontmatter type refusal {#root}

> Plan: [[plan-31-pre-mod-loose-ends]] ([[plan-31-pre-mod-loose-ends#t1]])
> Status: drafting (revision 2 after ch-bsd r2, ruling L147; fold tables at [[#rev-r1]] and
> [[#rev-r2]])
> Depends on: 0.83.1 / 0.84.0 deployed (it changes the raising input of 0.83.1's S2 and M2
> tests). Order, fixed by ruling L139 ([[plan-of-plans#rulings]]): 31.3 → 31.4 → **31.1** →
> 31.6. It needs 31.3's shared gate-tree helper and lands its upstream lint commit on top of
> 31.4's ([[#r3-upstream]]); it is never in flight together with 31.4 or 31.6.
> Closes: bug-244 (the ingest side), bug-255 (the lint side), bug-258 (the skip that two
> routes drop), **bug-264** (a plain edit of a synced GMD doc drops its anchors' inbound
> edges; live, moved here from 31.2 by ruling L144) and **bug-206** (a memory keeps the
> anchor of a heading deleted in place; closed here by ruling L148, [[#r6-removed-scope]]),
> all in [[bug_registry#registry]].
> Decision: `plan-31 D11`, decided in [[plan-of-plans#decisions]] ([[#d11]]).
> Base for every measurement here: `f3a508f` (2026-11-15).

rel: part-of -> [[plan-31-pre-mod-loose-ends]]
rel: implements -> [[plan-31-pre-mod-loose-ends#t1]]
rel: depends-on -> [[bug_registry#registry]]
rel: depends-on -> [[plan-review-2026-11-13#lead]]
rel: depends-on -> [[orchestration#planning]]
rel: depends-on -> [[plan-of-plans#decisions]]
rel: depends-on -> [[task-bug179-lint-ingest-anchor-parity]]
rel: depends-on -> [[plan-31b-spec-census]]
rel: reinforces -> [[feedback_no_silent_failures]]
rel: reinforces -> [[feedback_errors_fail_loudly_on_the_console]]
rel: related-to -> [[task-31.6-one-wikilink-resolver]]
rel: related-to -> [[project_fleet_roster_1114]]

## Why {#why}

One markdown file whose frontmatter `id:` is a list makes the batched GMD pass raise, and
0.83.1's fallback then registers **every** markdown file of the tree as a plain doc, on that
ingest and on every later one. The per-file guard that should have caught it wraps the parse
only, and the parse accepts the list. The fix is to make the parser's result well typed, so the
guard that already exists catches the file, and to carry the skip to the person who ran the
command: on two of the routes a per-file skip is counted today and printed nowhere. {#why-body}

## Measured at `f3a508f` (2026-11-15) {#baseline}

Scripts and outputs: [[plan-31b-spec-census]]. Probes ran dev code on throwaway stores under a
short `/tmp` root; no live store was opened. {#baseline-how}

### Where the list raises {#baseline-raise}

`frontmatter_probe_a.py`, output `workflow/review-output/spec31b-frontmatter-probe.log`:

| Frontmatter | `parse_gmd` | docs route (`ingest_gmd_paths`, strict and lenient) | memory route (`as_memory=True`) and `plan_memory_refresh` |
|---|---|---|---|
| `id: [a, b]`, or `id:` followed by `- a` / `- b` | returns `doc_id=['a', 'b']` | `TypeError: cannot use 'list' as a dict key` at `ingest_gmd.py:1435` (`file_hashes[doc.doc_id]`) | the same `TypeError` at `ingest_gmd.py:1243` (`_parse_memory_walk`, `claims.setdefault`) |
| `title: [a, b]`, or `title:` followed by list items | returns `title=['a', 'b']` | `TypeError: expected string or bytes-like object, got 'list'` at `ingest_gmd.py:797` (`_title_concept_tokens`) | the same on the bridge; `plan_memory_refresh` passes |
| `id:` with no value, or `id: []` | falls back to the stem (strict, memory) or the path (lenient) | ingests; both docs present | ingests |
| `title:` with no value | falls back to the doc id | ingests | ingests |
| a plain file (no `gmd:` key) with `id: [a, b]` | `None` strict; a list id lenient | strict: counted non-GMD. Lenient (the `rmx ingest` route): the `:1435` `TypeError` | the `:1243` `TypeError` |
{#baseline-raise-table}

- Every raise is past the per-file guards (`ingest_gmd.py:1386` and `:1233`), which wrap
  `parse_gmd` only. One file fails the batch on all three routes. {#fact-past-guard}
- The minimal parser (`_parse_frontmatter`) produces only strings and lists, so "non-string"
  means a list. `id: 123`, `id: true` and a date all parse as strings. {#fact-only-lists}
- `frontmatter_probe_b.py`: eleven other odd shapes do **not** fail the batch (a NUL in the id,
  title or body; `tags:` or `imports:` as a string; `gmd:` as a list; `#` in the id; an
  unclosed frontmatter; an empty file; a lone `---`); a non-UTF-8 file is caught by the
  existing guard and lands in `skipped_unparseable`. {#fact-other-shapes}
- The lint has the same hole: `tools/gmd/lint.py` on a list `id:` exits 1 with a Python
  traceback that names no file (`key in docs` in `main._ingest`, outside its `try`), and
  passes a list `title:` with 0 errors, which the ingester raises on. Registered as bug-255:
  the two sides disagree on which frontmatter types are legal. {#fact-lint}

### Where a per-file skip is reported today {#baseline-report}

`IngestStats.skipped_unparseable` holds `(path, error)`. Who reads it:

| Route | Call site | The skip reaches the caller? |
|---|---|---|
| `rmx ingest-gmd` (in-process, and the daemon job) | `cli.py:11053`, `daemon.py:3770` | yes: `stats.report()` prints the count and each path |
| `rmx ingest-gmd --as-memory --dry-run` | `cli.py:10927`, `:10938` | yes (`cli.py:10946`) |
| the session-card index | `cli.py:14501` | yes: both branches print the report |
| `rmx ingest` / `rmx reingest` (code+docs) | `ingest.py:1515` in `_ingest_markdown_gmd` | **no**: only `.docs` is returned |
| `rmx sync`, the watcher, the async flush | `sync.py:372` in `_sync_paths` | **no**: only `.docs` is read |
{#baseline-report-table}

So on the two routes that carry edits, a file the guard skips (a non-UTF-8 file today, a
refused file after this task) is dropped from the graph with nothing printed. On the sync
route the batch call is not inside a `try` at all: a list `id:` in one edited file raises out
of `_sync_paths` and rolls back the whole batch's transaction. Registered as bug-258.
{#fact-silent-routes}

### What the sync route does with a refused file {#baseline-b1}

`sync_refusal_probe.py` ([[plan-31b-spec-census]]; output
`workflow/review-output/spec31b-sync-refusal-probe.log`), a throwaway store, `src/` untouched,
both designs simulated at run time. Doc `a` (id `adoc`, anchor `sec`) is synced, edited, then
given a list `title:`; doc `b` cites `adoc#sec`.

| Step | Arm A: R1 only (this spec's first draft) | Arm B: R1 and [[#r2-sync-order]] |
|---|---|---|
| flush 1, `a` now has a list title | `adoc` and `adoc#sec` are **gone**; only a fresh relpath row is left; nothing reports a refusal; tracked mtime == disk mtime | `adoc` 14 and `adoc#sec` 16 **unchanged**; `gmd_refused` names `a.md`; tracked mtime != disk mtime; `a.md` is back on the queue |
| flush 2, nothing changed | 0 paths, 0 touched: the file is skipped and the refusal is silent | 1 path, **refused again**; ids unchanged; still queued |
{#baseline-b1-table}

| Step | Arms A and B (the guard as it is) | Arm C: arm B and [[#r6]] (the guard purges only the relpath row) |
|---|---|---|
| sync 1, `a` and `b` | `adoc` 1, `adoc#sec` 3; `b` has 2 edges to `adoc#sec` | the same |
| sync 2, a plain edit of `a` | `adoc` 14, `adoc#sec` 16: **new ids**; `b`'s edges to `adoc#sec`: **0** | `adoc` 1, `adoc#sec` 3: unchanged; `b`'s edges: **2**; the relpath row is re-made (12 → 22) |
| flush 1 and flush 2, the list title | as the table above | refused both times; `adoc` 1, `adoc#sec` 3, the relpath row 22 and `b`'s 2 edges all unchanged |
{#baseline-bug264-table}

This is ch-bsd r1's B1, reproduced (arm A) and its fold shown to hold on the second flush
(arm B), as ruling L139 asks. {#fact-b1-probe}

The same probe shows **bug-264**, which ruling L144 admitted as live and moved into this
task: in arms A and B the plain edit of `a` (sync 2) drops `b`'s `rel:` edges to `adoc#sec`
(2 before, 0 after). The semantic pass re-creates the relpath-named `doc` row on every sync,
so the guard at `sync.py:269-271` fires on every edit of every synced GMD doc; its
`purge_path` takes the doc-id row and the anchors with their inbound edges; and the citing
doc is unchanged, so nothing writes the edges back until a forced reingest. The code+docs
route has the same guard (`ingest.py:1508`). Learning being off does not prevent it. Arm C
shows the fix of [[#r6]] holding. {#fact-inbound-edges}

### How many files have the shape {#baseline-fleet}

`frontmatter_census.py`, reading each file with the ingester's own `_parse_frontmatter`. Repos
are the fleet roster ([[project_fleet_roster_1114]]), found from the known list
([[feedback_fleet_discovery_known_list_no_tree_walk]]), each walked as the code+docs ingest
walks it (`GMD_EXTS`, `should_ignore`). Output `workflow/review-output/spec31b-frontmatter-census.log`.

| Scope | Markdown files | With frontmatter | list `id` | empty `id` | list `title` | empty `title` |
|---|---|---|---|---|---|---|
| refmatrix | 786 | 778 | 0 | 0 | 0 | 0 |
| cliquedb | 167 | 156 | 0 | 0 | 0 | 0 |
| viascope | 198 | 164 | 0 | 0 | 0 | 0 |
| orderly | 39 | 39 | 0 | 0 | 0 | 0 |
| cliquet | 47 | 47 | 0 | 0 | 0 | 0 |
| atldb | 30 | 24 | 0 | 0 | 0 | 0 |
| atlftpd | 41 | 40 | 0 | 0 | 0 | 0 |
| thiquet | 156 | 139 | 0 | 0 | 0 | 0 |
| **eight repos** | **1,464** | **1,387** | **0** | **0** | **0** | **0** |
| every Claude memory dir (30, of which 20 non-empty) | 1,057 | 1,031 | 0 | 0 | 0 | 0 |
{#baseline-fleet-table}

No file in the fleet has the shape. The fix therefore changes no live store, and needs no
reingest or fleet step. One memory file outside this project nests `id:` under `metadata:`;
the parser flattens it onto the top-level key, which there happens to equal the stem. That is
not this task ([[#out-of-scope]]). {#baseline-fleet-body}

## Requirements {#requirements}

### R0: re-measure at base {#r0}

Run `frontmatter_probe_a.py`, `frontmatter_probe_b.py` and `frontmatter_census.py` at the
task's base sha and record the outputs in the summary. If the census finds a file with the
shape, stop and tell the lead: the release then has a live-store consequence this spec says it
does not have. {#r0-body}

### R1: `parse_gmd` returns typed fields or raises {#r1}

`parse_gmd` raises `GmdFrontmatterError` (a `ValueError`, defined in `ingest_gmd.py`) when the
frontmatter `id` or `title` is a **non-empty list**. The message names the key and the value:
`frontmatter `id` must be a string, got a list: ['a', 'b']`. From then on `GmdDoc.doc_id` and
`GmdDoc.title` are always `str`. {#r1-body}

- The check is one function, `ingest_gmd.frontmatter_refusal(path)`: the reason a file is
  refused before it is parsed (it cannot be read as UTF-8; its `id` or `title` is a non-empty
  list), or nothing. `parse_gmd` calls it after `_parse_frontmatter` and before the
  `gmd`-key test, and raises on a list; the sync route calls the same function before it
  purges anything ([[#r2-sync]]). So the rule has one text, and it covers strict, lenient and
  `memory_ids` parses, and a plain file read leniently.
  `_parse_frontmatter` is unchanged: it also feeds `tags:` and `imports:`, which are lists by
  design, and the memory body split at `ingest_gmd.py:1500`. {#r1-where}
- An empty value (`id:`, `id: []`, `title:`) stays what it is today, absent: the fallback id
  and title apply ([[#baseline-raise-table]]). The parser cannot tell `id:` from `id: []`, and
  no file has either. {#r1-empty}
- No guard is added in the batch passes. The two per-file guards that exist catch the raise
  and append `(path, "GmdFrontmatterError: …")` to `skipped_unparseable`. {#r1-guard}

### R2: the refused file is named on every route {#r2}

A file in `skipped_unparseable` reaches the caller on the two routes that drop it today
([[#baseline-report-table]]). The shape is the one 0.83.1 built for a failed pass (ruling L112
S2) and 26.2 built for a refused sync path: the rest of the batch lands, then the command
fails naming the files. {#r2-body}

- **`rmx ingest` / `rmx reingest`.** `_ingest_markdown_gmd` adds each `(path, error)` to a
  list on the store beside `gmd_pass_failures`; the daemon's `ingest_path` op returns the
  delta as `gmd_files_skipped` (a list of `[path, error]`); the in-process branch of
  `cli._ingest` builds the same field. `ingest.gmd_pass_failure_message` stays the one place
  that turns the result into a sentence: with skipped files and no failed pass it returns
  `GMD pass skipped N markdown file(s) under <path>: <path>: <error> | …; the other M were
  GMD-parsed. Fix the file(s) and re-run.` The CLI raises it as its `Error:` line (exit 1), and
  the `ingest_path_start` job records it as its top-level `error`, exactly as for a failed
  pass. {#r2-ingest}
- **`rmx sync`, the watcher, the async flush.** A new report key `gmd_refused` holds
  `[path, error]` rows, the form of `memory_ownership_errors`. One accessor in `sync.py`
  returns both lists, and the five readers of `memory_ownership_errors` use it (`sync.py:209`
  and `:230`, `daemon.py:3211` and `:3526`, `cli.py:9062`): `refusal_summary`,
  `raise_if_refused`, the recorded sync error of the watch and async-flush routes, and the
  queue's re-enqueue. {#r2-sync}
- **The refusal comes before the purge, and the refused file is not "touched"** (ch-bsd r1
  B1). Two passes of `_sync_paths` undo a refusal that is only reported:
  `_sync_one`'s GMD dispatch purges the whole path when a relpath-named `doc` row exists
  (`sync.py:269-271`), and the semantic pass re-creates that row on every sync, so the purge
  runs on every edit, before the GMD pass can refuse; and the semantic pass then stamps the
  file's mtime (`mark_tracked`), so the next sync skips the file and the next clean flush
  clears the recorded error. Probed: [[#fact-b1-probe]]. So:
  1. `_sync_one` calls `frontmatter_refusal` for a GMD file **before** the guard. A refused
     path returns as refused: nothing at the path is purged, it is not put on `gmd_paths`,
     and so it is not in `touched_existing` (no semantic pass, no `mark_tracked`). Its
     previous doc row and anchors stay, with their ids.
  2. A path the GMD pass itself skips for another reason (`skipped_unparseable` after the
     batch call) is added to `gmd_refused` and **removed from `touched_existing`** before the
     semantic passes run. For such a path the purge has already run: it is absent until it
     is fixed, and the `Error:` line says so.
  3. Because the mtime is never stamped for a refused path, every later sync of it reaches
     `_sync_one` again and refuses again; `flush_queue` puts it back on the dirty queue; the
     watch and async-flush routes record the error on every flush and never see the clean
     flush that would clear it.
  {#r2-sync-order}
- **The stored row.** On the sync route the refused file's previous doc and anchor rows are
  kept as they were, by step 1 above. On the code+docs route (`rmx ingest`) the relpath row
  is purged before the batch call as today; the refused file is then absent until it is
  fixed, and the `Error:` line says so. {#r2-row}
- **Routes that already print it** keep their report and their exit status. {#r2-unchanged}

That the two routes exit non-zero is `plan-31 D11`, decided ([[#d11]]). {#r2-decision}

### R3: the lint refuses the same shapes (bug-255) {#r3}

`tools/gmd/lint.py`'s `parse_doc` reports a non-empty list `id:` or `title:` as an **error**
on line 1, `bad-frontmatter-type`, with the key and the value: one issue line, exit 1, no
traceback. The file's other checks still run, keyed by its filename stem, and it is left out
of the id table that cross-doc links resolve against, so the `key in docs` lookup that
crashes today never sees a list. {#r3-body}

- **The same rule on both sides.** The lint errors on exactly the values `parse_gmd` refuses
  ([[#r1]]): a non-empty list for `id` or `title`; an empty value is absent on both sides.
  The table of [[#baseline-raise-table]] is the shared fixture ([[#ac-9]]). {#r3-same-rule}
- **`name:`.** The lint still reads a legacy `name:` as the doc id when there is no `id:`
  (until [[task-31.6-one-wikilink-resolver#r1-name]] removes that). A list `name:` gets the
  same error. The ingester does not read `name:`, so this is lint-only and outside the
  parity rule. {#r3-name}
- **Upstream first.** `~/claude_tools/gmd/lint.py` is canonical and `tools/gmd/lint.py` is
  its byte-identical vendored copy ([[task-bug179-lint-ingest-anchor-parity#f-canonical]],
  [[task-bug179-lint-ingest-anchor-parity#d4]]): the change and its cases in
  `scripts/test-lint-gates.py` land upstream, then the file is re-vendored from that sha.
  {#r3-upstream}
- **On top of 31.4's commit** (ruling L139; L133 M8). 31.4 lands first and changes the same
  upstream file: an opt-in `--strict` flag (any warning makes the exit 1, and the summary
  line ends `(strict: warnings fail)`), passed by `scripts/lint-gmd.sh`, and
  `session/recall-state` added to `KNOWN_MEMORY_TYPES` (read from
  `task-31.4-retire-standing-warnings` on `spec-plan31a` at `3225a16`). This task's upstream
  commit is made on that one, its re-vendor keeps both, and `bad-frontmatter-type` is an
  error with or without `--strict`. 31.6's commit then goes on top of this one. {#r3-order}

### R4: the S2 and M2 tests get a registered patch {#r4}

Ruling L112a ([[plan-review-2026-11-13#lead]]): fixing bug-244 removes the real raising input
of four tests, and this task's RED gives them "another real raising input or a registered patch
of `ingest_gmd_paths`". This spec takes the patch. {#r4-body}

- The tests: `test_s2_the_ingest_op_result_counts_a_failed_gmd_pass` (two params) and
  `test_s2_rmx_ingest_fails_loudly_naming_the_gmd_pass` (two routes) in
  `tests/test_bug241_r2_l112.py`; `test_m2_a_failed_gmd_pass_is_reported_at_the_top_of_the_job_record`
  in `tests/test_bug241_r3_l114.py`. They pin the fallback chain: `_ingest_markdown_gmd`'s
  `except` → the store counter → the op result → the CLI and the job record. {#r4-tests}
- The patch: a fixture script `tests/fixtures/rmx_gmd_pass_raises.py` that replaces
  `refmatrix.ingest_gmd.ingest_gmd_paths` with a function that raises
  `RuntimeError("injected GMD pass failure")`, then runs the console script's entry point with
  its own `argv`. `_ingest_markdown_gmd` imports the name at call time, so the patch is in
  force in whichever process runs the pass. {#r4-patch}
- Where it runs: on the daemon routes the test starts the daemon as that script in the
  foreground (`daemon start --no-watch --no-detach`) and drives it with the unpatched `rmx`;
  on the in-process route the CLI itself is that script. The socket, the op, the CLI and the
  job record stay real. {#r4-where}
- It is a patch of a dependency of the unit under test, never of the unit, and gets a row in
  `workflow/test_mock_registry.md` (the lead allocates the id). The tests' docstrings stop
  saying "No mocks". {#r4-registry}
- `BAD_MD` leaves those four tests and moves to this task's new tests ([[#ac-2]],
  [[#ac-3]]), where the same file must now be skipped and named. {#r4-bad-md}

### R5: the gate checks the two sides agree {#r5}

`scripts/check-gmd-parity.py`'s `scan()` compares, for every file in scope (before it skips a
file the lint does not treat as GMD): the lint reported `bad-frontmatter-type` for `id` or
`title`, against `parse_gmd` raised `GmdFrontmatterError`. When both refuse, the lint's error
line is the report and the parity step adds nothing. When one refuses and the other does
not, it is a `[frontmatter-parity]` error naming the file and which side refused. A raise of
any other kind stays a `[parity-parse-fail]`. {#r5-body}

### R6: an edit of a GMD doc keeps its anchors and their inbound edges (bug-264) {#r6}

The GMD dispatch never purges the whole path. At its two sites, `sync._sync_one`
(`sync.py:269-271`) and the code+docs markdown pass (`ingest.py:1508-1509`), the call
`purge_path(abs)` becomes `Store.purge_legacy_relpath_doc(rel, abs)`, which removes **only**
the `doc` row named by the file's relpath, so that the semantic pass writes that row's links
fresh. {#r6-body}

- It never touches the doc-id row, an anchor, or an `entity_links` row that has one of them
  at either end. The GMD pass then updates those rows in place, as it does for a doc that
  has no relpath row. {#r6-not-touched}
- It deletes no `tracked_files` row and logs no `untrack`: the path is the doc-id row's path
  too, and the semantic pass stamps it. {#r6-tracked}
- It is one `purge_entity` of one id, with that method's events (`unlink`, `tombstone`). A
  path with no relpath row is a no-op, as the guard is today. {#r6-one-row}
- **What stays 31.2's.** This is the GMD-dispatch half of
  [[task-31.2-learned-evidence-agreement#r3]], moved by ruling L144 because it is live. A
  learned row on the relpath row is still lost with that row here, exactly as it is today;
  keeping it (the row survives when it carries a learned row, only its non-learned links and
  evidence go, with an `evidence_clear` event, and the guard looks at non-learned rows)
  is 31.2's refinement of the same method. The name is 22.6 R4's; the row is not legacy
  ([[#fact-inbound-edges]]). {#r6-31-2}
- **With [[#r2-sync-order]].** The refusal still comes first: a refused file's relpath row
  is not purged either, so its semantic links stay those of its last good version.
  {#r6-order}

**What the edit removed goes with it** (ch-bsd r2 S1, ruling L147). The whole-path purge was
also the only thing that dropped an anchor an edit deleted; with the narrow purge alone a
removed `{#sec}` stays in the graph with its hierarchy edge, its body-term mentions and its
inbound edges (8 links in ch-bsd's probe, `bsd31b-r2-stale-anchor-probe.log`). That is
bug-206's class, on every synced doc. So the GMD pass removes what the new text no longer
names: {#r6-removed}

- **Which rows.** When `ingest_gmd_paths` re-derives a file, on any route, after pass 1 has
  written the new parse: every GMD row at the file's path (literal or resolved) that the new
  parse did not produce. That is each anchor concept (`meta.gmd_node`) whose name is not
  one of the new parse's node names, and, on a non-memory route, a `doc` row at the path
  whose name is neither the new doc id nor the relpath (the row a changed `id:` leaves
  behind). {#r6-removed-rows}
- **On the bridge** (`as_memory=True`) the file is a memory and the anchors judged are that
  memory's own `<id>#…` concepts. 26.2's keep in `purge_path` protects exactly those rows
  from a purge of the path, which is why a heading deleted in place left its anchor for as
  long as the memory lived (bug-206). This rule does not go through `purge_path`: the
  memory's own re-derive decides, from its own new text, which of its anchors still exist.
  The `memory` row itself is never removed here, whatever the file's `id:` now says:
  forgetting a memory is `forget_memory`'s. On a non-memory route an anchor that a memory
  owns is never selected. {#r6-removed-bridge}
- **How.** One `purge_entity` per row, so every link at either end goes and each is logged.
  Counted on `IngestStats.anchors_removed`, with the names, and printed in the report and
  on the routes of [[#r2]] when non-zero. The doc row and every anchor the new parse still
  has are not touched and keep their ids. {#r6-removed-how}
- **Inbound `rel:` edges from other docs go with the anchor, as stale; their lines become
  pending.** A citing doc's line to the removed anchor now points at nothing. Its edge is
  removed by the purge. For each such edge that has a `rel:` evidence row, that evidence row
  is deleted and a pending row is written for the citer (`add_pending_ref`, with the row's
  file, line and link as written), so that the line is counted as unresolved by the recount,
  the lint's `dangling-anchor` names it at the gate, and it binds again with no edit to the
  citer if the anchor comes back (bug-216 R10's rule, applied at the moment the target
  disappears). {#r6-removed-inbound}
- **With 31.6's unlink rule.** [[task-31.6-one-wikilink-resolver#r5]] unlinks the re-derived
  doc's own outgoing `rel:` edges that its new text no longer states, by that doc's evidence
  keys. An inbound edge from another doc is never one of those keys, so R5 does not see it;
  this rule removes it with the anchor. An outgoing edge of the removed anchor itself goes
  with the anchor here, and R5 then finds that key already gone. The removal runs first
  (after pass 1), R5 after the doc's pass-2 writes. {#r6-removed-r5}
- **Scope: every route, one function** (ruling L148). Sync, the code+docs pass, `ingest-gmd`
  on docs, and the bridge. The bridge never had the whole-path purge, so there the defect is
  older than this task: it is bug-206, a stale anchor concept on a memory, and it closes
  here. The inbound-edge rule of [[#r6-removed-inbound]] is the same on the bridge: a
  memory's `rel:` line to another memory's removed anchor becomes a pending row.
  {#r6-removed-scope}

## Acceptance criteria {#acceptance}

Each names its test and its kind. New tests live in `tests/test_bug244_frontmatter_refusal.py`
unless said otherwise. {#acceptance-intro}

- **AC-1: the parser refuses the two shapes and nothing else.** Parametrised over
  [[#baseline-raise-table]]'s rows and the eleven shapes of [[#fact-other-shapes]], for strict,
  lenient and `memory_ids`. A non-empty list `id` or `title` raises `GmdFrontmatterError`
  naming the key; every other shape returns what it returns at base. **RED** at base for the
  list rows (the E line is `DID NOT RAISE`); **characterization** for the rest. {#ac-1}
- **AC-2: one bad file does not demote the batch.** A tree of three GMD docs plus `BAD_MD`,
  through `ingest_gmd_paths` (docs strict, docs lenient, `as_memory=True`) and
  `plan_memory_refresh`: no raise; `skipped_unparseable` holds exactly the bad path with a
  `GmdFrontmatterError` text; the three good docs have their doc row **and** their anchor
  nodes. The same with a list `title`. **RED** at base (E line: the `TypeError` of
  [[#baseline-raise-table]]). {#ac-2}
- **AC-3: `rmx ingest` names the file, and the rest is GMD-parsed.** Through a real daemon and
  in-process (the two routes of the S2 test), the tree of AC-2: the op result's
  `gmd_files_skipped` names the bad path; `gmd_pass_failed` is 0; the good docs' anchors
  exist (asserted with `rmx query` or a snapshot read); the CLI prints one `Error:` line
  naming the path and the count, and exits 1 (`plan-31 D11`). The
  agent route's job record carries the same sentence at its top level. **RED** at base (E
  line: `gmd_pass_failed > 0` and the "registered as plain docs" message, or the missing
  field). {#ac-3}
- **AC-4: `rmx sync` names the file and keeps the rest.** A project with two changed GMD docs
  and one changed doc whose `title:` is now a list, through `_sync_paths`, through `rmx sync
  -f` in-process and through a real daemon: the two good docs are updated; the bad doc's
  previous doc row and anchors are unchanged, **ids included**, its relpath-named row is
  unchanged too (same id, same semantic links), and a `rel:` edge from another doc to one of
  its anchors is still live; the report's `gmd_refused` names it; the CLI
  prints the `refusal_summary` line and exits 1; the daemon's watch route records a sync
  error that `rmx daemon status` prints; the path is back on the dirty queue after a
  `flush_queue`. The bad doc was synced once before, so its relpath row exists and the guard
  would fire. **Then a second `flush_queue` with nothing changed:** it refuses the same path
  again, the ids are still unchanged, the file's tracked mtime is still not its disk mtime,
  the recorded error is still there and `rmx daemon status` still prints it. Fixing the file
  and flushing again clears the error and updates the doc. **RED** at base (E line: the
  `TypeError` out of `_sync_paths`); with R1 alone the second-flush leg is RED (E line: 0
  paths touched, no refusal), which is [[#fact-b1-probe]]'s arm A. {#ac-4}
- **AC-5: a file the guard already skipped is no longer silent.** The non-UTF-8 file of
  [[#fact-other-shapes]] through AC-3's and AC-4's routes, the second flush included: named
  the same way, and on the sync route its previous rows are kept. The fixture carries `---`
  and `gmd:` as ASCII in its first 512 bytes and the bad bytes after them: `is_gmd_file`
  sniffs only that head (`ingest.py:84`), and a file that does not sniff as GMD goes down the
  plain-doc route and is never refused (ch-bsd r1 M2). A second leg makes the GMD pass skip a
  file for a reason the pre-check does not know (a patched `parse_gmd` that raises for one
  path, registered like [[#r4-patch]]): it is in `gmd_refused`, is not stamped, and is
  refused again on the second flush ([[#r2-sync-order]] step 2). **RED** at base (E line: no
  `gmd_files_skipped` / `gmd_refused`; the command says nothing). {#ac-5}
- **AC-6: the fallback chain still works.** The four tests of [[#r4-tests]], re-pointed at the
  registered patch in the RED phase, pass at base and after GREEN, and their two guards (clean
  tree, unpatched) pass. **Characterization.** The summary also records the old `BAD_MD`
  versions of the four failing at the GREEN commit: the proof that the old input is gone and
  that the re-point was needed. {#ac-6}
- **AC-7: the lint names the file.** `tools/gmd/lint.py` on a directory holding a good doc
  and, in turn, each list shape of [[#baseline-raise-table]]: one `bad-frontmatter-type`
  error on line 1 of the bad file naming the key, exit 1, no `Traceback` in the output, and
  the good doc's own issues unchanged. A list `name:` with no `id:`: the same error. An empty
  `id:` or `title:`: no such error. **RED** at base (E lines: the `TypeError` traceback for a
  list `id:`; exit 0 with 0 errors for a list `title:`). The same cases are added to the
  upstream `scripts/test-lint-gates.py`. {#ac-7}
- **AC-8: the fleet has no such file.** R0's census output, zero in every column of
  [[#baseline-fleet-table]]. **Measurement.** {#ac-8}
- **AC-9: lint and ingest refuse the same files.** One parametrised test over every row of
  [[#baseline-raise-table]] and every shape of [[#fact-other-shapes]]: the lint reports
  `bad-frontmatter-type` for `id` or `title` **if and only if** `parse_gmd` raises
  `GmdFrontmatterError`, for the strict, lenient and `memory_ids` parses. **RED** at base (E
  lines: for a list `title:` the lint says nothing and the ingester raises `TypeError` later;
  for a list `id:` the lint crashes). {#ac-9}
- **AC-10: the gate fails when the two sides differ.** `check-gmd-parity.scan()` on (i) a
  scratch dir with a list-`title` doc: no parity finding (both refuse; the lint's error is
  the report); (ii) the same dir with the lint's check disabled (a gate tree built by 31.3's
  shared helper with a text override of `tools/gmd/lint.py` that lacks it,
  [[#tests-helper]]): one `[frontmatter-parity]` finding naming the file
  and "ingester only"; (iii) the repo scope: 0 findings. **RED** at base (E line: no such
  finding kind; (ii) returns nothing). (ii) is the must-fail input that proves the check can
  fail ([[feedback_clean_corpus_hides_a_dead_gate]]). The lint with its check removed is a
  test double of the unit's dependency, and gets its own row in
  `workflow/test_mock_registry.md` beside [[#r4-registry]]'s; the lead allocates the id
  (ch-bsd r1 M15). {#ac-10}
- **AC-11: an edit keeps the anchors and their inbound edges (bug-264).** The probe's shape,
  through the real `_sync_paths` with its semantic pass: docs `a` (id `adoc`, anchor `sec`)
  and `b` (a `rel:` line to `adoc#sec`) are synced; `a` is edited and synced; then edited
  and synced again. After each edit: `adoc` and `adoc#sec` have the ids of the first sync;
  `b`'s edges to `adoc#sec` are live, with their evidence rows; `a`'s own new body terms are
  indexed; the relpath row exists (re-made) and its semantic links are this version's, none
  doubled; no `untrack` event for the path is in `facts.log`. The same through
  `rmx ingest <tree>` run twice with `a` edited between (the twin), and through a real
  daemon's watch flush. **RED** at base (E lines: `adoc#sec` has a new id; `b`'s edges to it
  are 0), which is [[#baseline-bug264-table]]'s middle column. **The removed-heading leg**
  (ch-bsd r2 S1): `a` has `{#sec}` and `{#keep}`; `b` cites `adoc#sec`; both are synced
  twice. `a` is edited to drop the `sec` heading and synced. Asserted: no entity named
  `adoc#sec` exists and no `entity_links` row has its old id at either end (its hierarchy
  edge, its body-term mentions and `b`'s edge are gone); `adoc`, `adoc#root` and `adoc#keep`
  keep their ids; `b`'s line has a pending row and no `rel:` evidence row;
  `anchors_removed` is 1 and names it. Then `{#sec}` is put back and `a` synced: `b`'s edge
  to the new `adoc#sec` is live again though `b` was never touched. A second variant
  changes `a`'s `id:`: the `doc` row under the old id and its anchors are gone, the rows
  under the new id exist. All of it also through `rmx ingest` (the twin). **RED** at base
  only together with R6's narrow purge: at base the whole-path purge removes the anchor and
  everything else with it, so this leg is written against the R6 tree and its RED run is
  recorded there (E line: `adoc#sec` still exists with 8 links, as ch-bsd's probe). **The
  bridge leg (bug-206, ruling L148):** memories `m` (headings `{#sec}` and `{#keep}`) and
  `n` (a `rel:` line to `m#sec`) are bridged with `ingest-gmd --as-memory`; `m`'s `sec`
  heading is deleted in place and the dir is bridged again. Asserted: no entity named
  `m#sec` exists and no link has its old id at either end; the `memory` row `m` and `m#keep`
  keep their ids and `m`'s content is the new text; `n`'s line has a pending row; the
  bridge's report prints `anchors_removed: 1` with the name; a `purge_path` of `m`'s file
  afterwards still keeps `m#keep` (26.2's keep is unchanged). Then the heading is put back
  and the dir bridged: `n`'s edge to `m#sec` is live again though `n` was not touched.
  **RED** at base (E line: `m#sec` still exists after the second bridge), which is bug-206
  as registered. {#ac-11}

## Must-fail mutations {#mutations}

Committed first, restored one at a time; each must make a test **fail**, not hang.

| # | Mutation | Must turn RED |
|---|---|---|
| 1 | drop the `id` half of R1's check | AC-1 (list-id rows), AC-2 |
| 2 | drop the `title` half | AC-1 (list-title rows), AC-2's title leg |
| 3 | move the check into the strict branch only (after the `gmd`-key test) | AC-1's plain-file lenient row, AC-2 lenient |
| 4 | `_ingest_markdown_gmd` stops recording `skipped_unparseable` | AC-3, AC-5 |
| 5 | the `ingest_path` op drops `gmd_files_skipped` from its result | AC-3 (daemon route only; the in-process route stays green, which is the point of having both) |
| 6 | `_sync_paths` stops filling `gmd_refused` | AC-4, AC-5 |
| 7 | the accessor of [[#r2-sync]] returns `memory_ownership_errors` only | AC-4 (the CLI line, the recorded error, the re-queue) |
| 8 | the fixture script stops patching (calls the real function) | AC-6's four tests |
| 9 | refuse an empty `id:` too | AC-1's empty rows (characterization), AC-9 |
| 10 | the lint checks `id` only | AC-7 (list `title:`), AC-9 |
| 11 | the lint reports the error and still adds the doc to its id table | AC-7 (the traceback returns) |
| 12 | the lint also errors on an empty `title:` | AC-7's empty leg, AC-9 |
| 13 | `scan()` compares only files the lint treats as GMD | AC-10, with a plain file whose `id:` is a list |
| 14 | `scan()` reports nothing when one side refuses | AC-10 (ii) |
| 15 | `_sync_one` asks `frontmatter_refusal` after the guard's purge | AC-4 (the relpath row is gone and is not re-made, because the refused file is not touched) |
| 19 | the sync site calls `purge_path` again | AC-11 (new anchor ids; `b`'s edges 0) |
| 20 | the code+docs site (`ingest.py:1508`) calls `purge_path` again | AC-11's `rmx ingest` leg |
| 21 | `purge_legacy_relpath_doc` also purges rows whose `path` is the file | AC-11 |
| 22 | `purge_legacy_relpath_doc` does not purge the relpath row | AC-11 (the semantic links are doubled or stale after the second edit) |
| 23 | `purge_legacy_relpath_doc` deletes the `tracked_files` row | AC-11 (an `untrack` event appears) |
| 24 | the removed-anchor step is skipped | AC-11's removed-heading leg (`adoc#sec` still exists, with its links) |
| 25 | the removed-anchor step purges every anchor at the path, kept ones too | AC-11 (`adoc#keep` has a new id) |
| 26 | an inbound `rel:` edge to a removed anchor leaves no pending row | AC-11's put-back step (`b`'s edge does not return) |
| 27 | the stale `doc` row of a changed `id:` is kept | AC-11's second variant |
| 28 | the removed-anchor step is skipped on the bridge route (`as_memory`) | AC-11's bridge leg (`m#sec` still exists) |
| 29 | on the bridge the step selects through `purge_path`'s memory-anchor keep | AC-11's bridge leg (the keep protects the stale anchor: bug-206 again) |
| 30 | on the bridge the step also removes the `memory` row of an id the file no longer carries | AC-11's bridge leg, with `m`'s `id:` changed: the old memory row is still there |
| 16 | a refused path stays in `touched_existing` | AC-4's second flush (0 paths touched, the error cleared) |
| 17 | `flush_queue` does not put a GMD-refused path back | AC-4's second flush on the queue route |
| 18 | step 2 of [[#r2-sync-order]] dropped (a path the pass skipped is still stamped) | AC-5's second leg |
{#mutations-table}

## Caller census {#census}

`parse_gmd` (the function that gains a raise), at `f3a508f`:

| Caller | On a raise today | After R1 |
|---|---|---|
| `ingest_gmd.py:1385` (docs pass 1) | caught, `skipped_unparseable` | the refused file lands here |
| `ingest_gmd.py:1230` (`_parse_memory_walk`: the bridge and `--dry-run`) | caught, `skipped_unparseable` | the same |
| `ingest_gmd.py:123` (`prestage_hashes`) | caught, counted `skipped` | the same |
| `sync.py:59` (`_gmd_route_pending`) | caught, returns `False` | the same: the file is not forced onto the GMD route by this probe; the mtime gate still sends a changed file there |
| `scripts/check-gmd-parity.py:94` | reported as `parity-parse-fail` | compared with the lint's own refusal ([[#r5]]) |
| `scripts/check-rel-landing.py:93` | listed under `parse failures`, not counted | the same |
{#census-parse}

`ingest_gmd_paths` (whose result gains a reader): `cli.py:11053`, `cli.py:14501`,
`daemon.py:3770`, `ingest.py:1515`, `sync.py:372`; `plan_memory_refresh` at `cli.py:10927`
and `:10938`. The first three and the last two print the report; `ingest.py:1515` and
`sync.py:372` are the two R2 changes. Readers of `memory_ownership_errors`: the five sites of
[[#r2-sync]]. Tests that import the changed modules are listed by grep at the task's base and
named in the summary ([[orchestration#task]] step 4). {#census-result}

## Files {#files}

- `src/refmatrix/ingest_gmd.py` (R1: `GmdFrontmatterError`, the check in `parse_gmd`).
- `src/refmatrix/ingest.py` (`_ingest_markdown_gmd` records the skips;
  `gmd_pass_failure_message`).
- `src/refmatrix/daemon.py` (`ingest_path` op result; the watch and async-flush readers).
- `src/refmatrix/store.py` (`purge_legacy_relpath_doc`, R6; after 29.5, the removal module),
  and the two call sites in `sync.py` and `ingest.py`.
- `src/refmatrix/sync.py` (`gmd_refused`, the accessor, `refusal_summary`,
  `raise_if_refused`, `flush_queue`).
- `src/refmatrix/cli.py` (`_ingest`'s in-process result; the sync refusal line). If 29.5 has
  split `cli.py`, these are the modules its map gives `_ingest` and `_sync_in_process`.
- `tests/gmd_gate_tree.py` is used, not copied ([[#tests-helper]]).
- New `tests/test_bug244_frontmatter_refusal.py`; new `tests/fixtures/rmx_gmd_pass_raises.py`;
  `tests/test_bug241_r2_l112.py` and `tests/test_bug241_r3_l114.py` (R4).
- `workflow/test_mock_registry.md` (the R4 row), `workflow/bug_registry.md` (bug-244), the
  implementation summary. Registry ids are the lead's.
- Upstream repo `~/claude_tools/gmd/` (first): `lint.py`, `scripts/test-lint-gates.py`,
  `SPEC.md` §2 (`id` and `title` are strings; a list is an error).
- `tools/gmd/lint.py` (re-vendored from that sha), `docs/gmd/SPEC.md`,
  `scripts/check-gmd-parity.py` (R5).
- `docs/INTEGRATION.md`'s ingest section: one sentence on a refused file.
{#files-list}

## Risks {#risks}

- **The upstream lint.** The lint change lands in `~/claude_tools/gmd` and is re-vendored.
  31.4 and 31.6 change the same upstream file; the order is fixed, 31.4 → 31.1 → 31.6, never
  two in flight, each upstream commit on top of the previous ([[#r3-order]]). A re-vendor
  from a sha that lacks an earlier task's commit would drop its fix (the bug-068 shape);
  `test_ac8_vendored_tool_is_a_committed_upstream_blob` and 31.4's `--strict` case catch it.
  viascope runs the upstream lint directly: no file there has the shape
  ([[#baseline-fleet-table]]), so nothing new fails. {#risk-upstream}
- **A louder sync.** A file that was silently skipped (non-UTF-8) now fails `rmx sync` and the
  post-commit hook's background sync records an error until the file is fixed or ignored.
  That is the intent of [[feedback_errors_fail_loudly_on_the_console]]. The census already
  counts such files as `unreadable`: 0 in all eight repos and all 30 memory dirs, re-run by
  ch-bsd, so no command starts failing at the deploy for this either. {#risk-louder}
- **A doc that stays refused holds a stale row.** On the sync route the refused file keeps
  the rows of its last good version until it is fixed. The recorded error names it for as
  long as that lasts. {#risk-stale-row}
- **The exception type.** `raise_if_refused` raises `MemoryOwnershipError`, whose name is wrong
  for a GMD refusal. The CLI catches that class to print a clean line. The implementer either
  raises a shared parent that the two CLI handlers catch, or keeps one class and says so; the
  AC fixes the output, not the class. {#risk-class}
- **The foreground daemon in a test.** The R4 fixture runs `daemon start --no-detach` as a
  child; it must be stopped in teardown and must sit under the suite's sandbox like every
  other spawned `rmx`. bug-253's `.venv-eval` lookup applies to these tests too. {#risk-fixture}
- **`RMX_INGEST_NODE_YIELD_EVERY=x`** still makes `ingest_gmd_paths` raise (`ValueError` at
  `ingest_gmd.py:1329`, probed). It was the other candidate for [[#r4]] and was not taken: it
  is an unhardened knob (the `envknob` shape the queue review names beside bug-188), so a test
  built on it would lose its input a second time. It is not fixed here. {#risk-knob}

## Out of scope {#out-of-scope}

- A real YAML parser, or typing of other keys. `tags:` and `imports:` are already guarded.
- Nested `metadata:` keys flattened onto top-level keys (one file fleet-wide, harmless there).
- Hardening the env knobs of [[#risk-knob]].
- Per-doc isolation of store-level failures inside the GMD pass. After this task no measured
  file shape fails the batch; the batch `except` stays as the backstop the R4 patch tests.
{#out-of-scope-list}

## Test trees {#tests-helper}

Every test here that needs the gate's scripts in a throwaway tree (AC-7, AC-9, AC-10) builds
it with 31.3's shared helper, `tests/gmd_gate_tree.py`, which copies exactly the files
`scripts/lint-gmd.sh` declares on its `# gate-file:` lines and takes per-file text overrides
(`task-31.3-ledger-anchor-guard` `#r6` on `spec-plan31a` at `3225a16`; rulings L133 B2 and
L139). AC-10 (ii)'s lint without the check is such an override. No test here copies
`lint-gmd.sh` or `lint.py` into a tree by hand; 31.3's bypass check would fail it. This task
adds no `# gate-file:` line: it adds no file to the gate. {#tests-helper-body}

## Revision 1: fold of ch-bsd r1 (ruling L139) {#rev-r1}

The review read `a4d245a`; some findings were already folded at `d788602`.

| Finding | Fold | Where |
|---|---|---|
| B1 the sync route loses the refused file's rows and the refusal goes quiet | the check runs before the guard's purge; a refused path is not touched or stamped; the second flush refuses again. Probe, both arms | [[#r2-sync-order]], [[#r2-row]], [[#r1-where]], [[#ac-4]], [[#ac-5]], mutations 15-18, [[#baseline-b1]] |
| M1 decisions and closures not written as decided | D11 cited as decided (L125); the header closes bug-244, bug-255, bug-258 (at `d788602`) | header, [[#d11]], [[#ac-3]] |
| M2 the non-UTF-8 count is measured; AC-5's fixture must sniff as GMD | the risk cites `unreadable` 0; the fixture's head is stated | [[#risk-louder]], [[#ac-5]] |
| S3 / L139 the linter order | 31.4 → 31.1 → 31.6, each upstream commit on the previous | header, [[#r3-order]], [[#risk-upstream]] |
| L133 M8 name 31.4's linter change | `--strict` and the `session/recall-state` enum line | [[#r3-order]] |
| L144: bug-264 moves here from 31.2 | the GMD dispatch purges only the relpath row; a requirement, an AC in the probe's shape, five mutations; the probe's arm C | [[#r6]], [[#ac-11]], mutations 19-23, [[#baseline-bug264-table]] |
| M15 (updated report) AC-10 (ii)'s lint double needs a mock-registry row | stated, for the lead to number | [[#ac-10]] |
| L133 B2 the shared gate-tree helper | `tests/gmd_gate_tree.py`; no fourth copy | [[#tests-helper]], [[#ac-10]] |
| bug-255, bug-258 (the lead; L132) | folded at `d788602` | [[#r3]], [[#r5]], [[#ac-7]], [[#ac-9]], [[#ac-10]] |
{#rev-r1-table}

## Revision 2: fold of ch-bsd r2 (ruling L147) {#rev-r2}

| Finding | Fold | Where |
|---|---|---|
| S1 the narrow purge no longer drops an anchor the edit deleted | the GMD pass removes the rows at the path that the new parse no longer names (anchors, and the `doc` row of a changed id); inbound `rel:` edges go with the anchor and their lines become pending; the interplay with 31.6's unlink rule is stated; a removed-heading leg and five mutations | [[#r6-removed]], [[#r6-removed-rows]], [[#r6-removed-inbound]], [[#r6-removed-r5]], [[#r6-removed-bridge]], [[#ac-11]], mutations 24-30 |
{#rev-r2-table}

Ruled since (L148): bug-206 closes here, so the removed-anchor rule serves the bridge too
([[#r6-removed-bridge]], [[#r6-removed-scope]], AC-11's bridge leg, mutations 28-30); the
pending-row conversion stays ([[#r6-removed-inbound]]). {#rev-r2-l148}

## Decisions {#decisions}

Decisions live in [[plan-of-plans#decisions]] and [[plan-of-plans#rulings]]; this section
cites them and records none of its own. {#decisions-rule}

- **`plan-31 D11`, decided** by ruling L125 on the recommendation (2026-11-15): a refused
  markdown file on `rmx ingest` and `rmx sync` does not stop the batch; the rest lands, then
  the command prints one `Error:` line naming each file and exits 1, as the same commands do
  for a failed GMD pass (L112 S2) and a refused memory path (26.2). Amended into
  [[#r2-ingest]], [[#r2-sync]], [[#ac-3]] and [[#ac-4]]. The option not taken was a line on
  stderr and exit 0, as `rmx ingest-gmd`'s report does. {#d11}
- **Ruling L148:** bug-206 closes here (the bridge route, one function); the pending-row
  conversion of [[#r6-removed-inbound]] stays. {#l148}
- **Ruling L147:** ch-bsd r2's finding on [[#r6]] folds ([[#rev-r2]]). {#l147}
- **Ruling L144:** bug-264 is live and is fixed here ([[#r6]]); 31.2 keeps the learned-row
  halves of its R3. {#l144}
- **Ruling L132:** bug-258 folds in here; bug-255 was folded in by the lead with the lint
  and ingest sides under one rule ([[#r3]], [[#r5]], [[#ac-9]], [[#ac-10]]). {#l132}

**Design proposed by this spec, for review** (not ledger decisions): the check is in
`parse_gmd`, not in `_parse_frontmatter` ([[#r1-where]]); an empty value stays absent on both
sides ([[#r1-empty]]); R4 takes the registered patch, not another raising input
([[#risk-knob]]); the parity check runs in the docs gate, beside the anchor parity
([[#r5]]). {#decisions-proposed}
