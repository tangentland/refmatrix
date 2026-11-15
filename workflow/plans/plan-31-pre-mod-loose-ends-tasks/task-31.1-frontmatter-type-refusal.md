---
gmd: "0.1"
id: task-31.1-frontmatter-type-refusal
title: "Task 31.1: a non-string frontmatter id or title is refused per file, named on every route, and no longer fails the GMD batch (bug-244)"
tags: [task, plan-31, gmd, ingest, frontmatter, batch-failure, bug-244]
metadata:
  node_type: task
  status: drafting
  plan: plan-31-pre-mod-loose-ends
  created: 2026-11-15
  updated: 2026-11-15
---

# Task 31.1: frontmatter type refusal {#root}

> Plan: [[plan-31-pre-mod-loose-ends]] ([[plan-31-pre-mod-loose-ends#t1]])
> Status: drafting (ch-architect on Fable, 2026-11-15; ch-bsd spec review next)
> Depends on: 0.83.1 / 0.84.0 deployed (it changes the raising input of 0.83.1's S2 and M2
> tests). Lands before [[task-31.6-one-wikilink-resolver]]: both edit `ingest_gmd.py`.
> Closes: bug-244 ([[bug_registry#registry]]).
> Base for every measurement here: `f3a508f` (2026-11-15).

rel: part-of -> [[plan-31-pre-mod-loose-ends]]
rel: implements -> [[plan-31-pre-mod-loose-ends#t1]]
rel: depends-on -> [[bug_registry#registry]]
rel: depends-on -> [[plan-review-2026-11-13#lead]]
rel: depends-on -> [[orchestration#planning]]
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
  passes a list `title:` with 0 errors. {#fact-lint}

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
of `_sync_paths` and rolls back the whole batch's transaction. {#fact-silent-routes}

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

- The check sits in `parse_gmd`, after `_parse_frontmatter` and before the `gmd`-key test, so
  it covers strict, lenient and `memory_ids` parses, and a plain file read leniently.
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
- **`rmx sync`, the watcher, the async flush.** `_sync_paths` reads
  `gmd_stats.skipped_unparseable` into a new report key `gmd_refused` (`[path, error]` rows,
  the form of `memory_ownership_errors`). One accessor in `sync.py` returns both lists, and
  the five readers of `memory_ownership_errors` use it (`sync.py:209` and `:230`,
  `daemon.py:3211` and `:3526`, `cli.py:9062`): `refusal_summary`, `raise_if_refused`, the
  recorded sync error of the watch and async-flush routes, and the queue's re-enqueue. A
  refused GMD file is re-queued like a refused memory path, so the recorded error stays until
  the file is fixed. {#r2-sync}
- **The stored row.** The refused file's previous doc and anchor rows are kept as they were
  (the GMD pass writes nothing for a file it does not parse). On the code+docs route the
  legacy relpath row is purged before the batch call as today; the refused file is then
  absent until it is fixed, and the `Error:` line says so. {#r2-row}
- **Routes that already print it** keep their report and their exit status. {#r2-unchanged}

Whether the two routes exit non-zero is `plan-31 D11` ([[#decisions]]). {#r2-decision}

### R3: the gate names the file {#r3}

`scripts/check-gmd-parity.py` already reports a file either parser raises on
(`[parity-parse-fail]`, exit 1). After R1 it names a refused file with the
`GmdFrontmatterError` text. No change to the script: an AC proves it. The lint's own error for
the shape is upstream work and rides [[task-31.6-one-wikilink-resolver#r7]]'s upstream commit,
so that this task touches `src/` and `tests/` only. {#r3-body}

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
  naming the path and the count, and the exit status is the one `plan-31 D11` picks. The
  agent route's job record carries the same sentence at its top level. **RED** at base (E
  line: `gmd_pass_failed > 0` and the "registered as plain docs" message, or the missing
  field). {#ac-3}
- **AC-4: `rmx sync` names the file and keeps the rest.** A project with two changed GMD docs
  and one changed doc whose `title:` is now a list, through `_sync_paths`, through `rmx sync
  -f` in-process and through a real daemon: the two good docs are updated; the bad doc's
  previous doc row and anchors are unchanged; the report's `gmd_refused` names it; the CLI
  prints the `refusal_summary` line; the daemon's watch route records a sync error that
  `rmx daemon status` prints; the path is back on the dirty queue after a `flush_queue`.
  **RED** at base (E line: the `TypeError` out of `_sync_paths`). {#ac-4}
- **AC-5: a file the guard already skipped is no longer silent.** The non-UTF-8 file of
  [[#fact-other-shapes]] through AC-3's and AC-4's routes: named the same way. **RED** at base
  (E line: no `gmd_files_skipped` / `gmd_refused`; the command says nothing). {#ac-5}
- **AC-6: the fallback chain still works.** The four tests of [[#r4-tests]], re-pointed at the
  registered patch in the RED phase, pass at base and after GREEN, and their two guards (clean
  tree, unpatched) pass. **Characterization.** The summary also records the old `BAD_MD`
  versions of the four failing at the GREEN commit: the proof that the old input is gone and
  that the re-point was needed. {#ac-6}
- **AC-7: the repo gate names a refused file.** `check-gmd-parity.scan()` on a scratch dir
  holding one list-`title` GMD doc returns a failure whose text holds the path and
  `GmdFrontmatterError`. **RED** at base (E line: the failure list is empty: lint and the
  ingester both parse it). {#ac-7}
- **AC-8: the fleet has no such file.** R0's census output, zero in every column of
  [[#baseline-fleet-table]]. **Measurement.** {#ac-8}

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
| 9 | refuse an empty `id:` too | AC-1's empty rows (characterization) |
{#mutations-table}

## Caller census {#census}

`parse_gmd` (the function that gains a raise), at `f3a508f`:

| Caller | On a raise today | After R1 |
|---|---|---|
| `ingest_gmd.py:1385` (docs pass 1) | caught, `skipped_unparseable` | the refused file lands here |
| `ingest_gmd.py:1230` (`_parse_memory_walk`: the bridge and `--dry-run`) | caught, `skipped_unparseable` | the same |
| `ingest_gmd.py:123` (`prestage_hashes`) | caught, counted `skipped` | the same |
| `sync.py:59` (`_gmd_route_pending`) | caught, returns `False` | the same: the file is not forced onto the GMD route by this probe; the mtime gate still sends a changed file there |
| `scripts/check-gmd-parity.py:94` | reported as `parity-parse-fail` | names the refused file ([[#r3]]) |
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
- `src/refmatrix/sync.py` (`gmd_refused`, the accessor, `refusal_summary`,
  `raise_if_refused`, `flush_queue`).
- `src/refmatrix/cli.py` (`_ingest`'s in-process result; the sync refusal line). If 29.5 has
  split `cli.py`, these are the modules its map gives `_ingest` and `_sync_in_process`.
- New `tests/test_bug244_frontmatter_refusal.py`; new `tests/fixtures/rmx_gmd_pass_raises.py`;
  `tests/test_bug241_r2_l112.py` and `tests/test_bug241_r3_l114.py` (R4).
- `workflow/test_mock_registry.md` (the R4 row), `workflow/bug_registry.md` (bug-244), the
  implementation summary. Registry ids are the lead's.
- `docs/INTEGRATION.md`'s ingest section: one sentence on a refused file.
{#files-list}

## Risks {#risks}

- **A louder sync.** A file that was silently skipped (non-UTF-8) now fails `rmx sync` and the
  post-commit hook's background sync records an error until the file is fixed or ignored.
  That is the intent of [[feedback_errors_fail_loudly_on_the_console]]; the count in the fleet
  is not measured for non-UTF-8 files and R0 adds it to the census. {#risk-louder}
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
- The lint's error for the shape: [[task-31.6-one-wikilink-resolver#r7]].
- Per-doc isolation of store-level failures inside the GMD pass. After this task no measured
  file shape fails the batch; the batch `except` stays as the backstop the R4 patch tests.
{#out-of-scope-list}

## Decisions {#decisions}

**For the user: `plan-31 D11`.** A refused markdown file on `rmx ingest` and `rmx sync`:

- **(a) recommended: the rest lands, then the command fails.** One `Error:` line naming each
  file, exit 1; on the routes with no terminal, a recorded sync error and the job's top-level
  `error`. It is what the same two commands do today for a failed GMD pass (L112 S2) and for a
  refused memory path (26.2), and the user's rule for a sync that stops on an error. No file
  in the fleet has the shape, so no command starts failing at the deploy.
- (b) named on stderr, exit 0. Matches `rmx ingest-gmd`'s report, which prints the skip and
  exits 0. A hook that discards stderr would then hide it.
{#d11}

**Taken in this spec** (for the lead to register): the check is in `parse_gmd`, not in
`_parse_frontmatter` ([[#r1-where]]); an empty value stays absent ([[#r1-empty]]); R4 takes
the registered patch, not another raising input ([[#risk-knob]]); the lint half rides 31.6's
upstream commit ([[#r3]]); the pre-existing silent drop of `skipped_unparseable` on the
ingest and sync routes is fixed here because the refusal would otherwise trade a loud batch
failure for a silent per-file one ([[#fact-silent-routes]]). {#decisions-taken}
