---
gmd: "0.1"
id: task-29.5-split-giant-modules
title: "Task 29.5: split the giant modules — cli.py becomes the package refmatrix/cli/ by command group, store.py is split by concern, by tool-made moves under equality gates"
tags: [task, plan-29, refactor, cli, store, module-size, mechanical-move, census, code-quality]
metadata:
  node_type: task
  status: pending
  plan: plan-29-code-quality
  created: 2026-11-14
  updated: 2026-11-14
---

# Task 29.5: split the giant modules {#root}

> Plan: [[plan-29-code-quality]] ([[plan-29-code-quality#t5]])
> Status: Pending
> Depends on: [[task-29.4-suite-health]] through its stage 5: T0.7's clean run on the sharded
> runner is this task's baseline, and the runner's `--compare` is the equality gate around
> every commit. [[task-29.1-registry-triage]] (rows this task touches are closed in its
> grammar).
> Runs third in plan-29's order: 29.1 → 29.4 → **29.5** → 29.2 ∥ 29.3.
> **Runs alone and is released alone:** in an announced window with no other `src/` work in
> flight ([[#r9]]).
> Before the first move: an ADR for the module layout and import layering, authored by
> `ch-architect` ([[#r1]]).
> **Decided by the user on 2026-11-14 (ruling L106), and built to here** ([[#user-decisions]]):
> plan-29 D17 (the size default, with a sixth criterion); plan-29 D4 = (c) (a normalised derive
> hash, in 29.2); `plan-review-fable D4` (a standing go that excludes this task's release);
> `plan-review-fable-store D5` (duckdb 1.5.3 before baselines).
> **Still open, the user's:** **plan-29 D23** (the learned rows at the merge, [[#decisions]]).
> User gates: the window's start (the lead announces it; the user may hold it); **each phase's
> merge into the dev tree, which is a store event** ([[#r9-store-event]]); this task's release,
> which needs its own go; and plan-29 D23.

rel: part-of -> [[plan-29-code-quality]]
rel: implements -> [[plan-29-code-quality#t5]]
rel: depends-on -> [[task-29.4-suite-health]]
rel: depends-on -> [[task-29.1-registry-triage]]
rel: depends-on -> [[tdd-governance]]
rel: related-to -> [[plan-review-2026-11-13#p1]]
rel: reinforces -> [[feedback_converge_repeated_shapes]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: reinforces -> [[feedback_family_list_misses_generated_checks]]
rel: reinforces -> [[feedback_compare_failures_by_error_not_name]]
rel: reinforces -> [[feedback_commit_before_mutation_revert]]
rel: reinforces -> [[feedback_no_silent_failures]]

**How other documents are cited here.** As in [[task-29.4-suite-health#citing]]: **T0**, the
**queue review**, the **store review** and the **memory review** are not on this spec's
branch, so their ids and anchors are written as code (`T0#r0-1`, queue review `#b2`). The same
holds for the two sibling specs, `task-29.2-mypy-gate` and `task-29.3-converge-shapes` (branch
`spec-plan29b`). {#citing}

## Why {#why}

`cli.py` is 15,212 lines and `store.py` is 9,246. Every 0.83.0 merge conflicted in `cli.py`,
`verbs.py` or `mcp.py`. A reviewer who fixes one call site cannot see its siblings 9,000 lines
away, and that is the defect class the 0.83.0 rounds kept finding
([[plan-29-code-quality#why]]). The user set the target at about 3,000 lines per module
([[plan-29-code-quality#decisions]] D3). {#why-body}

A split is also the most dangerous kind of change to review by reading: the diff is 25,000
lines that are meant to say nothing. So this task does not ask anyone to read it. It builds a
set of gates that compare what the program **is** before and after, makes every move with a
tool, and commits one group at a time so a gate that goes red names a small commit.
{#why-method}

## Measured at `f3709d2` (2026-11-14) {#baseline}

Static reads, plus one import of `refmatrix.cli` in the dev interpreter to walk the real click
tree (no command was run and no store was opened). Logs in `workflow/review-output/`:
`plan29a-click-tree.log`, `plan29a-cli-map.log`, `plan29a-store-census.log`,
`plan29a-private-census.log`, `plan29a-citation-census.log`, `plan29a-cli-refs.log`. The scripts
that made them are in `workflow/measurements/plan-29-spec-census/` ([[plan-29-spec-census]]).
{#baseline-method}

| Measure | Value |
|---|---|
| modules over 3,000 lines | `cli.py` 15,212; `store.py` 9,246; `daemon.py` 7,355; `verbs.py` 3,653; `ingest.py` 3,144 |
| `src/refmatrix/*.py` total | 75,255 lines, 73 modules |
| **click tree** | 219 commands and groups: 213 visible, 6 hidden aliases; 25 groups; 627 parameters; 90 top-level names (22 groups, 62 visible commands, 6 hidden aliases) |
| callbacks | 213 functions, 9,756 lines. Every callback is defined in `cli.py` |
| other top-level defs in `cli.py` | 158 (141 private), 5,201 lines; 255 lines of imports, constants and module state |
| a structural dump of the tree (every command's path, help, parameters, defaults, flags) | 282,261 bytes |
| **`store.py`** | one class, `Store`: 7,968 lines, 191 methods (63 private), 18 section banners; 1,278 lines before the class (31 functions and small classes, the derive tables) |
| `Store` internals that would break a move | 0 name-mangled attributes (`self.__x`), 0 `super()`, 12 references to `Store` by name |
{#baseline-table}

### What reaches into the two modules {#baseline-reach}

| Measure | Value |
|---|---|
| test files that import `cli` / `store` | 140 / 220 |
| **test patches on `refmatrix.cli` attributes** (`monkeypatch.setattr`, `mock.patch`) | 191 sites, 13 names: `_root` 160, `_partition_override` 7, `_resolve_partition` 6, `main` 3, `_reexec_for_fork_safety` 3, `_store` 3, `_memory_partition_default` 2, `_grep_stdin_addendum` 2, and five names once each |
| test reads of `cli` privates (`cli._name`) | 150 sites, 45 names; 27 of the names (101 sites) are helpers the proposed map moves into a command module |
| test patches on `refmatrix.store` **module** attributes | 15 sites: `_DERIVE_SRC_DIR` 4, `derive_code_hash` 4, `time` 2, `_DERIVE_CODE_MODULES` 2, `__file__` 2, `is_memory_only_root` 1 |
| tests that read the modules' **source or path** | `"cli.py"` path literals: 18 sites in 9 files; `"store.py"`: 27 in 9; `<module>.__file__`: 4 + 4; `source_of(cli, …)`: 1; one non-recursive `glob("*.py")` over `src/refmatrix` (`test_task21_1_agent_usage_report.py:267`), which would not see a subpackage |
| census allow lists keyed on `module:qualname` | 8 entries naming `cli:` or `store:`, all in `tests/test_bug212_r4_red.py` |
| test files that name `cli.py` or `store.py` at all (queue review) | 31 |
| `python -m refmatrix.cli` spawn sites | 4 in `src/`, in 3 files: `daemon.py:7059`, `scheduler.py:131`, `ui/server.py:191` and `:578` (string constants in code, by syntax tree; three more matches are comments or docstrings). Test files that mention the form: 8 |
| `src` modules that import from `cli` | 2: `handoff.py` (three private names, lazily, "cli->handoff cycle") and `telemetry.py` (`main`) |
| `global` statements in `cli.py` | 4, all `_partition_override` (lines 931, 8404, 8477, 11921; by syntax tree) |
| references from one proposed command module to a def in another | 3: `queue_clear` → `sync`; `_reingest_embed` → `embed_cmd`; `reingest` → `session_ingest_cmd`. The core references no def the map moves out of it |
| defs in command modules that use a **local** name equal to a `cli` def (a parameter called `rebuild`, `partition`, `top`, `watch`, `stats`) | 48 |
{#baseline-reach-table}

The queue review counted the same surface by grep: 185 `monkeypatch.setattr(cli, …)` sites in
64 files (159 on `_root`) and 49 private names. The counts here are from the syntax tree, and
include string targets and `mock.patch`: 191 and 45. The two agree on what matters. R0's
inventory is the list that binds. The first revision of this table said 5 `global` statements
and 7 spawn sites in 6 files: both counted text in comments and docstrings (ch-bsd r1 `#m4`).
The counts above are from `plan29a-r2-xrefs.log`. {#baseline-reach-two-counts}

### Private names used across modules {#baseline-private}

| Direction | Sites | Distinct (module, name) | Files |
|---|---|---|---|
| `src` → `src`, all modules | 76 | 55 | 24 |
| ... into `launchctl` / `scan` / `store` / `ingest` / `daemon` / `handoff` / `verbs` / `cli` | 14 / 10 / 9 / 9 / 6 / 5 / 4 / 3 | 10 / 5 / 4 / 7 / 5 / 4 / 4 / 3 | |
| tests → `src` | 742 | 244 | 170 |
{#baseline-private-table}

From `cli`: `_subject_link`, `_subject_upsert`, `_sync_memory_dir` (all taken by `handoff.py`).
From `store`: `_CONCEPT_SHIFT`, `_ENTITY_MASK`, `_VERB_ALIASES`, `_concept_variants`.
{#baseline-private-names}

### Line citations in specs {#baseline-citations}

| Where | `cli.py:NNNN` | `store.py:NNNN` |
|---|---|---|
| `workflow/plans/` | 234 sites, 45 files | 134 sites, 27 files |
| ... in specs that are not completed (pending, approved, in-progress, drafting, blocked) | 271 sites for the two modules together, in 44 files | |
| all of `workflow/` (history included, `review-output/` excluded) | 759 sites, 224 files | 394 sites, 114 files |
| `docs/` | 8 | 13 |
{#baseline-citations-table}

The heaviest pending specs: 23.1 (35 sites), 19.0 (32), 22.6 (27), 25.1 (19), 17.1 (12). The
seven frozen spec branches are not in this count. The queue review counted the **effective**
copy of each spec (the spec-branch version where one exists): 53 documents with 280 citations
(148 `cli.py:N`, 132 `store.py:N`), or 50 and 249 without three shipped specs whose frontmatter
is stale; and 142 `daemon.py:N`, 58 `verbs.py:N` and 9 `mcp.py:N` besides. They are stale
already: the branches were cut at `1cf3b9f`, and `cli.py` has moved about 1,200 lines and
`store.py` 774 since. R0 counts again after the merges.
{#baseline-citations-note}

### Four facts that decide the design {#baseline-facts}

1. **Tests patch the module, and the code reads the patch through its own globals.** 160 tests
   set `cli._root` and then call a command. Today the command finds the patched `_root` because
   both live in one module. A command moved to another file, calling a `_root` it imported by
   name, would call the real one, against the test's intent and without an error. The split
   has to keep one namespace that is both what tests patch and what moved code reads.
   {#fact-patch}
2. **`cli.py` is run as a file.** `cli_entry` re-execs once on macOS for fork safety
   (`_reexec_for_fork_safety`: `os.execv(sys.executable, [sys.executable, *sys.argv])`). After
   `python -m refmatrix.cli …`, `sys.argv[0]` is the module's **file path**, so every spawned
   daemon is in fact `python …/src/refmatrix/cli.py daemon start` (bug-229's `ps` line shows
   it), with `src/refmatrix/` as `sys.path[0]`. As a package the same re-exec runs
   `…/cli/__main__.py` as a script, with `src/refmatrix/cli/` as `sys.path[0]`: any file there
   whose name matches a module the process imports later would shadow it. {#fact-argv}
4. **Under `-m`, the CLI is loaded twice today, and as a package it is loaded once.**
   `python -m refmatrix.cli` runs `cli.py` as the module `__main__` (the file ends
   `if __name__ == "__main__": cli_entry()`), and so does the re-exec. The commands run in
   `__main__`. When `handoff.py:669/699` or `telemetry.py:1011` then lazily import
   `refmatrix.cli`, Python loads the file **again**, as a second module with its own state
   (`_partition_override`, the caches). The four production spawn sites all use this form. The
   `rmx` console script does not: it imports `refmatrix.cli` and calls `cli_entry`, one copy.
   After the split `cli/__main__.py` imports `refmatrix.cli`, so `-m` processes have one copy
   too. That is a behaviour change on a production path, and the suite cannot see it: tests
   drive the CLI in-process as `refmatrix.cli` (ch-bsd r1 `#s5`). {#fact-identity}
3. **`store.py` is hashed by file name.** `store.derive_code_hash()` hashes the content of
   `("ingest.py", "ingest_gmd.py", "store.py")` (`_DERIVE_CODE_MODULES`), found beside
   `store.__file__`; a file it cannot read is skipped without a word ("a missing module is not
   a freshness signal"). Splitting `store.py` changes that hash, as any edit to it does, and
   moves code out from under it unless the list is extended. {#fact-derive}

## The proposed map {#map}

R0 re-computes both maps from the base sha. They are the starting proposal, with real numbers,
and the size gate in [[#r7]] is what binds. The numbers are from `plan29a-cli-map.log` and
`plan29a-store-map.log`.

### `refmatrix/cli/` {#map-cli}

Command callbacks go to the module of their top-level click name. A helper goes with its only
user; a helper used by two or more command modules, or by none inside `cli.py`, stays in the
package's `__init__.py`. Lines are what the tool would write at `f3709d2` (sum 15,212).

| Module | Lines | Callback lines | Helpers | Top-level click names |
|---|---|---|---|---|
| `cli/__init__.py` (the core) | 1,689 | 0 | 49 (1,434 lines) | the `main` group, `cli_entry`, `_reexec_for_fork_safety`, `_root`, `_store`, `_DaemonWriter`, `console`, module state; imports the command modules last |
| `cli/__main__.py` | new, ~5 | | | `from refmatrix.cli import cli_entry` then `cli_entry()` |
| `cli/memory_cmds.py` | 2,238 | 1,149 | 22 | `memory`, `taxonomy` |
| `cli/session_cmds.py` | 2,223 | 1,791 | 24 | `focus`, `session`, `task`, `save-state`, `recall-state`, `scan-prompt`, `cctree` |
| `cli/grep_cmds.py` | 1,504 | 250 | 21 (1,254 lines) | `grep`, alone |
| `cli/catalog_cmds.py` | 1,461 | 1,399 | 4 | `partition`, `replica`, `derive`, `repair-index`, `compact`, `compact-log`, `rebuild`, `checkpoint`, `dump-log`, `migrate-to-duckdb`, `merge-verb-aliases` |
| `cli/ingest_cmds.py` | 1,362 | 973 | 10 | `ingest`, `ingest-gmd`, `ingest-status`, `sync`, `reingest`, `tldr-warm`, `graphify-warm`, `init`, `import`, `export` |
| `cli/daemon_cmds.py` | 1,352 | 1,201 | 5 | `daemon`, `queue`, `watch`, `log`, `cli-log`, `telemetry`, `fingerprint` |
| `cli/hub_cmds.py` | 1,019 | 911 | 9 | `hub`, `bus`, `schedule`, `ui`, `projects`, `mcp`, `curator`, `refine` |
| `cli/query_cmds.py` | 809 | 674 | 4 | `query`, `describe`, `neighbors`, `top`, `co-occur`, `stats`, `info`, `list` (and its 3 hidden aliases), `run`, `save-query`, `primer`, `tools-primer`, `pagerank` |
| `cli/search_cmds.py` | 431 | 392 | 2 | `context`, `recall`, `locate` |
| `cli/graph_cmds.py` | 312 | 303 | 1 | `link`, `unlink`, `add` (and its 3 hidden aliases), `canon`, `concept`, `coref`, `pairs` |
| `cli/vectors_cmds.py` | 290 | 250 | 2 | `embed`, `search-dense` |
| `cli/removal_cmds.py` | 264 | 221 | 4 | `forget`, `untrack`, `vacuum`, `prune-noise`, `noise`, `unnoise`, `protect`, `unprotect`, `audit-same-as` |
| `cli/admin_cmds.py` | 144 | 144 | 0 | `install-hooks`, `upgrade`, `version` |
| `cli/learn_cmds.py` | 114 | 98 | 1 | `learn` |
{#map-cli-table}

- The largest module is 2,238 lines.
- **Five modules are small on purpose.** The store review asks that groups with CLI surface
  still to come have a home reserved, so that later work lands in one file and not in the
  core: `vectors` (17.1), `catalog` (18.2, 18.3), `learn` (16.x), `removal` (22.x), and the
  **grep block as one module**, so that 16.5's rewrite of it stays in one file. The grep
  helpers are 1,254 lines, which matches the queue review's count of the code 16.5 guts.
- The plan's "one module per command group" does not partition `cli.py` by itself: 68 commands
  sit directly on `main` (62 visible, 6 hidden aliases) and 158 defs are helpers. The table is
  the partition: every top-level name is in exactly one module (the script checks it).
{#map-cli-notes}

### `store.py` and its concern modules {#map-store}

`Store` stays one class with one name and one import path. Its methods move into mixin
classes in sibling modules; `store.py` keeps the module-level code, the class statement,
construction, connection, slots and transactions. The cut is **by method**, because the
section banners in the file are not reliable: `content_rank` (366 lines) sits under "bitmaps",
`grep_evidence` under "subjects", the derive stamps under "purge / track files", and
`merge_partition` (342 lines) under "lifecycle". Lines at `f3709d2` (sum 9,246; each method
with the comment lines above it):

| Module | Lines | Methods | Holds |
|---|---|---|---|
| `store.py` (core: **catalog and slots**) | 2,328 | 31 | the 1,278 lines before the class (constants, the derive tables, helper functions, `Entity`, the error classes); `__init__`, `init`, `_connect`, `_active_slot_path`, the schema migrations, `with_partition`, `_ensure_partition`, `_read`, `close`, `transaction`, `_log_event(s)`, `rebuild_entities_indexes`, `repair_entity_links_index` |
| `store_entities.py` | 1,106 | 31 | upsert and resolve; `describe_entity`, `explain_entity`; flags; saved queries; stats; the coref sidecar and pair index |
| `store_links.py` (**evidence and links**) | 905 | 23 | `link`, `unlink`, `bulk_link`, `link_many`, `deferred_links`, weights; `add_evidence`, `clear_rel_evidence`, `get_evidence`, `grep_evidence`; the pending `rel:` references; `denotes` |
| `store_memory.py` (**memory**) | 877 | 23 | the intuition memory layer; subjects; reinforcement; `_memory_compile_status` |
| `store_replay.py` (**replay**, `facts.log`) | 741 | 6 | `dump_catalog_to_log`, `rebuild_index_from_log`, `apply_log_delta`, `_apply_event_body`, `_apply_one_event`, `_replay_concept` |
| `store_removal.py` | 652 | 13 | `purge_entity`, `purge_path`, `fold_concept_dups`, `_bulk_purge_ids`, `untrack_by_path`, `vacuum`, `prune_noise` |
| `store_rank.py` | 641 | 11 | `content_rank` and the BM25 statistics it reads |
| `store_derive.py` | 540 | 14 | tracked files and their stamps; `stamp_derive`, `derive_status`, `derive_history` |
| `store_fragments.py` (**fragments / bitmaps**) | 526 | 19 | fragment load, flush and repair; `load_bitmap`, `save_bitmap`; linkage types; legacy fragment migration |
| `store_partition.py` | 522 | 5 | `merge_partition`, `rename_partition`, `_merge_pending_refs`; canon |
| `store_vectors.py` (**vectors**) | 408 | 15 | the Lance wrappers; pending embeddings |
{#map-store-table}

- The plan named four concerns (fragments/bitmaps, vectors, catalog and slots, memory). The
  store review found two that had no home: **evidence and links**, and **replay**. Six
  approved specs land in those two (bug-185, 16.6, 17.4, 22.2, 22.6, 23.5 R5), so they are
  modules of their own here.
- `apply_log_delta` and `_apply_event_body` (68 and 105 lines) have no caller in `src/` and are
  16.6's to delete (L50). If 16.6's deletion is separable it lands before phase 2
  ([[#r0]] item 9); if not, they move verbatim with the rest of replay.
{#map-store-notes}

## Requirements {#requirements}

### R0: re-measure, and inventory what the move can break {#r0}

At the task's base sha (after 29.4, after the frozen spec branches):

1. Re-run every count in [[#baseline]] and both maps. The summary shows old and new.
2. **The patch inventory:** every attribute of `refmatrix.cli` and `refmatrix.store` that any
   test sets or patches, from the syntax tree, with string targets (`"refmatrix.cli._root"`)
   included. This list decides what must stay late-bound ([[#r2]]).
3. **The read inventory:** every name any test or `src` module reads through those two modules
   (`cli._x`, `from refmatrix.cli import x`, `store._X`). This list decides the re-exports.
4. **The source-reader inventory:** every test that opens `cli.py` / `store.py` by path, reads
   `__file__`, calls `source_of` / `inspect.getsource` on them, enumerates `src/refmatrix` without
   recursion, or keys an allow list on `cli:` / `store:`. These are the only test files a move
   commit may edit ([[#r4]]).
5. **The argv and module-identity inventory:** which module state is per-copy in a `-m`
   process today ([[#fact-identity]]), who writes it in `__main__` and who reads it in the
   second copy, and so which outcomes differ today between `rmx <cmd>` and
   `python -m refmatrix.cli <cmd>`. Each difference is listed with the spawn site that can reach
   it. Then every reader of `sys.argv[0]` and every place a command line is
   matched as text (`discovery.pid_is_rmx`, `launchctl._rmx_path`, the sandbox's spawn parser,
   any test that asserts on `ps` output), each with what it sees before and after
   ([[#fact-argv]]). The naming census of [[#r2]] item 7 is run on the base tree too: a
   collision that exists today is a finding of its own, because today's daemons already run
   with `src/refmatrix/` first on their import path.
6. **The file-name inventory:** every place a module is named as a file: `_DERIVE_CODE_MODULES`,
   `_DERIVE_PASS_MODULES`, `pyproject.toml`'s package data, the hook generators, `eval/` and
   `scripts/` imports, `docs/`.
7. **The citation count** ([[#baseline-citations]]), again.
8. **What a derive-hash change does at deploy** ([[#fact-derive]]): which readers call
   `derive_code_hash()` with no pass name, what each prints or does when the value differs from
   a stored stamp, and so what the fleet shows after the store commits deploy. Written in the
   summary and in the deploy note. No guess: read the callers. {#r0-derive}
9. **Dead code that an approved spec deletes.** Code scheduled for deletion is deleted before
   it is moved, where its owner can do that separately: T0.4's `duckdb_view.py` and the
   `_read_via_duckdb` state, and T0.5's `brief.parse_gmd`, are gone by 29.4's stage 3. 16.6's
   `apply_log_delta` / `_apply_event_body` are checked here. This task deletes nothing itself:
   R0 lists what is still present and who owns it, and the lead decides whether the owner's
   deletion goes first.
10. **What must already be on `master`.** Anything small that touches `cli.py` or `store.py` and
    was meant to ride ahead: the 0.83.1 hotfix (bug-241, bug-240) and 25.1b's `legs_ms` timing
    pair, which the user placed before the split (L106). R0 lists
    each as merged or as explicitly held until after.
11. **The pins other specs hold on these files** ([[#r8]]): every unbuilt spec that walks
    `src/refmatrix/*.py` without recursion, or exempts a site by a qualified name such as
    `cli.compact` or `store.Store.rebuild_entities_indexes`, or keys an AST check on the file
    `store.py` or `cli.py`. The store review names the known ones: 18.2 R11/R13/AC-17, 18.3
    AC-14, 22.1a AC-8c, 22.2, 22.6 AC-6f, 16.6 AC-9c/9d/AC-12, bug-218 AC-2/AC-4b.
12. **The rows the merge will touch** ([[#r9-store-event]]). For every live store that holds rows
    keyed on `src/refmatrix/cli.py` or `src/refmatrix/store.py` (the dev tree's project store;
    the global store, if it holds any): the number of **learned** rows and of **protected** rows
    on each path, and what a row carries that grep cannot re-derive (a lifetime count, a
    first-learned time, provenance). Counted read-only, by the lead or through
    `scripts/rmx-master`, with the query written in the summary so it can be re-run after the
    merge. This task's agents do not open a live store.
13. **Baselines wait for duckdb 1.5.3.** `plan-review-fable-store D5` was decided: the dev venv
    is raised to the 1.5.3 floor. No gate golden, no derive-digest golden and no suite baseline
    is generated before that.

### R1: the decision is recorded first {#r1}

`ch-architect` authors the next ADR in `docs/adr/` (0006 at `f3709d2`), "module layout and
import layering", through `/ch-crucible`, before the first move commit, with a row in
`docs/adr/0000-adr-overview.md` and `docs/INDEX.md`. It records:

- **This is a file-size split, not a decomposition.** `Store` is still one class with one
  namespace and one lock; its methods live in several files. Composition (a `Store` made of
  collaborating objects) is a later decision, which 29.2's writer `Protocol` informs. The split
  must not be read as that decision, and must not make it harder.
- **The layering:** `cli` → `verbs` → the engine. The engine never imports `cli`. An import
  census enforces it, with two declared exceptions that each name an owner ([[#r2b]]).
- **One copy of the CLI in a `-m` process** is an accepted behaviour change
  ([[#fact-identity]], plan-29 D24).
- **The package rule:** a core that is read late by attribute ([[#r2]]); what `_name` means
  inside a package and across packages ([[#r6]]).
- **The ceiling** and its exception list ([[#r7]]), as plan-29 D17 was decided.

[[#r2]], [[#r2b]], [[#r5]], [[#r6]] and [[#r7]] are its inputs. If review of the ADR changes a
rule, this spec is revised before any code moves. {#r1-body}

### R2: the shape of `refmatrix/cli/` {#r2}

1. **`refmatrix.cli` stays the namespace.** `cli/__init__.py` is `cli.py`'s core: the `main`
   group, `cli_entry`, the shared helpers, the module state. A test that patches
   `refmatrix.cli._root` patches the same object in the same module as before. Helpers in the
   core call each other by bare name, as today, so a patch reaches them as today.
2. **Command modules read the core late.** A moved function refers to a core name as
   `_cli.<name>` (`from refmatrix import cli as _cli` at the top of the module). It never binds
   one with `from refmatrix.cli import <name>`. This is the one textual change a move makes
   ([[#r3]]), and it is what keeps [[#fact-patch]] true.
   - Applies to: every function, class, constant and piece of module state defined in the core,
     and to every imported module that the patch inventory names (a test that patches
     `cli.time` must still reach moved code).
   - Does not apply to: builtins, and imports that no test patches. The command module repeats
     the core's own import statement for those (standard library, third party, or another
     `refmatrix` module under the same alias), so the name is bound to the same object.
3. **Module state is assigned through the core.** `global _partition_override` followed by an
   assignment becomes `_cli._partition_override = …`. No command module holds a `global`
   statement for a name the core defines.
4. **A patched name does not move.** Any helper in the patch inventory stays in the core even
   when one command module is its only user (four helpers at `f3709d2`: `_grep_stdin_addendum`,
   `_memory_intent`, `_memory_daemon_call`, `_global_recall_rows`).
5. **A name that is read stays reachable.** For each name in the read inventory that moves (read
   by a test, by another `src` module, or by another command module, item 9), the
   core has one generated line, `from .<module> import <name>`, in a marked block. The block
   equals the inventory, exactly.
6. **Registration is by import.** `__init__.py` imports the command modules last, in a fixed
   order, after every core name exists. Each command keeps its decorator, written
   `@_cli.main.command(...)` or `@<group>.command(...)` for a group in the same module. A group
   and all its subcommands are in one module.
7. **Names.** Command modules are `<area>_cmds.py`. No file under `src/refmatrix/` or
   `src/refmatrix/cli/` has a stem equal to a standard-library module or to an installed
   top-level import name ([[#fact-argv]]). `src/refmatrix/cli.py` does not exist once the
   package does (a package and a module of one name: the package wins, silently).
8. **Entry points.** `refmatrix.cli:cli_entry` in `pyproject.toml` is unchanged.
   `python -m refmatrix.cli` works through `cli/__main__.py`, which imports by absolute name so
   that it also runs as a script after the re-exec. The re-exec itself is not changed. A `-m`
   process now has one copy of the CLI ([[#fact-identity]]); [[#r1]] records that as an accepted
   change, and [[#ac-4]] probes it.
9. **A command module never imports a sibling.** Three callbacks invoke a callback that the
   map puts in another command module (`queue_clear` → `sync`; `_reingest_embed` → `embed_cmd`;
   `reingest` → `session_ingest_cmd`). Such a reference is written `_cli.<name>`, like a core
   name, and the name joins the re-export block (item 5). It is resolved when the command
   runs, after every module has registered, so there is no import-order cycle, and a test that
   patches the name on `refmatrix.cli` still reaches the caller. R0 inventories these
   references from the syntax tree; the tool refuses a sibling reference it was not given.
10. **A local name is not a module name.** 48 defs in the command modules use a parameter or a
    local variable whose name equals a `cli` def (`rebuild`, `partition`, `top`, `watch`,
    `stats`). The substitution of item 2 applies to **free** names only. A local is never
    rewritten ([[#r3]]).

### R2b: the layering, its two declared exceptions, and the one move {#r2b}

The rule the ADR records is that the engine never imports `cli`. At `f3709d2` three places
break it. Whether a function can be moved down **now** is decided by what its **body** reads,
not by who reads its name: a function whose body reads a name that tests patch on
`refmatrix.cli` must stay where those patches land (ch-bsd r1 `#b1`; ruling L105). The bodies
were read from the syntax tree (`plan29a-r2-xrefs.log`):

| Engine site | Takes from `cli` | Its body reads (test-patched names in bold) | In this task |
|---|---|---|---|
| `handoff.py:699` | `_subject_upsert`, `_subject_link` | **`_root`**, **`_store`**, **`_memory_daemon_call`**; one call down, **`_resolve_partition`** | **stays** in `cli/__init__.py`; declared exception |
| `handoff.py:669` | `_sync_memory_dir` | **`_resolve_partition`**, **`_memory_partition_default`**, **`_partition_override`**, `_bridge_stats`, `_bridge_wait_for_active_job`, `_ingest_gmd_sync`; one call down, **`_root`** | **stays** in `cli/__init__.py`; declared exception |
| `telemetry.py:1011` (`_command_groups`) | `main` | it reads `main.commands`; **`main`** is patched at 3 sites (`tests/test_context_cost.py:142`, `:167`, `:192`), and a patched `main` sends it to its static fallback | **stays** as it is; declared exception |
| (none yet; 26.5 needs it from the engine) | `_root_from_projects_slug` | no `cli` name at all | **moves down** in phase 0b |
{#r2b-table}

1. **`_subject_upsert`, `_subject_link` and `_sync_memory_dir` are not moved by this task. They
   stay in `cli/__init__.py`.** (Ruling L105, B1.) {#r2b-stay}
   They stay in the core, so every patch on
   `refmatrix.cli` reaches them as it does today, and every test is unchanged. They are core
   names for the tool ([[#r2]] item 4 already keeps a patched name in the core; these are kept
   because their bodies read patched names). `handoff.py`'s two lazy imports stay as they are.
2. **`telemetry._command_groups` does not change.** It reads a patched name, lazily, and has a
   fallback that three tests reach through the patch. Handing the group names in from the CLI
   would change what those tests exercise.
3. **`_root_from_projects_slug` moves down**, in one ordinary commit: its body reads no `cli`
   name, nothing patches it, and it is called only from `cli.py` today. R0 names its home and
   says why. `cli` keeps the name bound to the same object. RED first: a test that the engine
   module that will need it can import it without importing `refmatrix.cli`.
4. **The census, with a declared allow list.** `tests/test_import_layering_census.py` fails on
   any import of `refmatrix.cli`, at module level or inside a function, from a `src/refmatrix`
   module outside the package, **except** the entries of its allow list. The list has exactly
   two entries, and each one records: the importing module and line, the names taken, the
   patched names their bodies read (the table above), and an **owner task id**.
   - An entry whose owner does not resolve to a spec under `workflow/plans/` fails the census.
   - An entry that no longer matches an import in the tree fails it too (a stale exception).
   - A third import fails it.
5. **The follow-up the owner builds** (not this task): one seam that lets tests patch one place.
   The CLI adapter resolves the root, the writer, the daemon call and the partition from its
   own (patchable) names and hands them to the engine function; AC-3-style probes show, for
   each patched name in the table, that a save-state run with the name patched on
   `refmatrix.cli` calls the patched object; then the functions move to their layer and the
   entries are deleted. It cannot start before 29.2's daemon-absent accessor exists: the
   helpers' in-process fallback needs a writer the engine does not have.
   - **Owner: `task-29.3-converge-shapes#slice-h`** (confirmed by that spec's author on
     2026-11-14; branch `spec-plan29b`, `6860150`). Slice h is 29.3's last slice: it hands one
     context to the engine functions, moves the three helpers, hands `telemetry` its group names,
     and takes this census's allow list from exactly two entries to empty. Both entries here
     name it. When 29.3's slice K moves this census onto its kit, it keeps both entries and the
     "owner must resolve" must-fail.
{#r2b-list}

### R3: every move is made by a tool {#r3}

`tools/split_module.py` reads a map file (`tools/split_maps/cli.json`, `store.json`: def name →
target module) and writes the result. "Mechanical" in this task means exactly: **the tool
produced it.**

- For each moved top-level def: its source lines, with the comments and blank lines directly
  above it, are moved verbatim; then the substitutions of [[#r2]] items 2 and 3 are applied
  from the syntax tree, and nothing else.
- For `Store` methods: the map is per method ([[#map-store]]). The method's lines move verbatim
  into a mixin class body (`class _StoreFragments:`), and module-level names of `store.py` that the method uses become
  `_st.<name>` (`from refmatrix import store as _st`), by the same rule.
- **Scope analysis is the tool's riskiest part, and replaying the tool cannot check it.** Two
  defences:
  - the tool's own tests include, RED first: a def whose parameter shadows a core name (not
    rewritten); a def whose local shadows a callback in another module (not rewritten); a
    nested function that reads the enclosing function's local of that name (not rewritten); a
    comprehension variable of that name (not rewritten); and the same four with the name used
    free (rewritten);
  - `tools/verify_split.py` checks every move **without the tool's scope logic**, from the
    compiler's own symbol tables (`symtable`): for each moved def, the names the compiler
    resolves as global after the move are the names it resolved as global before, minus the
    ones now read through `_cli` or `_st`, plus that alias; no name changed between local and
    global; and every global the def reads is bound in its new module. This is half of gate G8.
- `tools/split_module.py --check <parent-rev>` proves a commit: it re-runs the tool on the
  parent's tree with the commit's map and compares the output with the commit's tree, byte for
  byte, for every file under `src/`. It also prints, per moved def, that the def's syntax tree
  equals the parent's after undoing the substitutions.
- The tool refuses, naming the def: a moved def that assigns to a core name without the
  `_cli.` form; a `global` it cannot rewrite; a def whose free names it cannot resolve; a
  target module over the ceiling ([[#r7]]).
- A hand edit inside a move commit fails `--check`. A fix that the move makes necessary and
  the tool cannot make is its own commit, before the move, with its own test.

### R4: one group per commit, behind the gates {#r4}

**Order.** Phase 0 builds the gates. Phase 0b sets the layering rule. Phase 1 is
`cli`. Phase 2 is `store`. Phase 3 is the private names. Each commit lands on the task branch; the branch merges to `master` once, at
the end of a phase.

| Phase | Commits |
|---|---|
| 0 | the tool and its tests; the gates and goldens of this section, generated at the base sha and committed (the derive digest's golden among them, [[#r5-digest]]); the inventories of [[#r0]] |
| 0b | [[#r2b]]: the layering census with its two declared exceptions; `_root_from_projects_slug` moved down. Ordinary changes, not tool moves |
| 1 | `git mv cli.py cli/__init__.py` with `cli/__main__.py` (a rename and one new file; the source-reader tests that name the path are re-pointed here); then one commit per command module, smallest first: `learn_cmds`, `admin_cmds`, `removal_cmds`, `vectors_cmds`, `graph_cmds`, `search_cmds`, `query_cmds`, `hub_cmds`, `daemon_cmds`, `ingest_cmds`, `catalog_cmds`, `grep_cmds`, `session_cmds`, `memory_cmds` |
| 2 | one commit per concern module: `store_vectors`, `store_partition`, `store_fragments`, `store_derive`, `store_rank`, `store_removal`, `store_replay`, `store_memory`, `store_links`, `store_entities`; each extends `_DERIVE_CODE_MODULES` with its file ([[#r5]]) |
| 3 | [[#r6]], one commit per target module |
{#r4-phases}

**The baseline.** The suite is clean when this task starts: 29.4's stage 5 ends on T0.7's clean
run through the sharded runner, in the main tree, and commits that run's directory
([[task-29.4-suite-health#ac-7]]). Phase 0's first "before" is that run, at that sha, or a
re-run of it at this task's base sha if `master` has moved. A phase does not start on a suite
that is not clean. {#r4-baseline}

**The gates.** Every commit in phases 1 and 2 passes all of them. Each is generated at the
commit's parent and at the commit, and compared:

| Gate | What is compared | Must be |
|---|---|---|
| G1 the click tree | a structural dump of `refmatrix.cli.main`: for every command path, sorted: type, name, help, short help, epilog, hidden, deprecated, context settings, the callback's `__name__`, and for every parameter: name, option strings, type, required, default, nargs, multiple, is-flag, help, envvar, hidden (`tools/dump_click_tree.py`; 282,261 bytes at `f3709d2`) | byte-identical |
| G2 help text | `--help` output of all 219 paths at a fixed width, and `rmx tools-primer`'s output | byte-identical |
| G3 the generated docs | `scripts/gen-cli-tree.py --check` (the CLI tree in `docs/ARCHITECTURE.md`, the hooks table in `README.md`), which is `tests/test_docs_generated.py::test_cli_tree_section_equals_its_render` and `::test_hooks_table_section_equals_its_render` | exit 0, both tests green, the two doc sections unchanged |
| G4 the surfaces | for `refmatrix.cli` and `refmatrix.store`, three checks: (1) every name in the **read inventory** and the **patch inventory** still resolves on the module; (2) every other name that left is in the tool's map with its new home, and resolves there; (3) the names that appeared are exactly the expected ones, which the tool lists: the command submodules and the `_cli` alias on `refmatrix.cli`, the mixin classes and the `_st` alias on the store modules | all three hold; anything else is a failure that names the attribute |
| G5 the suite | `scripts/ptest.sh --tier all` at the parent and at the commit, then `--compare` ([[task-29.4-suite-health#r2]]) | equal by (node id, phase, E line), collected counts equal |
| G6 the dev tree | `scripts/ptest.sh --merge-gate` on the merged dev tree before each phase's merge commit ([[task-29.4-suite-health#r7]]), **with the dev daemon's watcher out**, as step 5 of [[#r9-store-event]] | passes; a red G6 is aborted with the store untouched |
| G7 parity and censuses | `tests/test_verb_parity.py` (167 tests), `tests/test_bug212_r4_red.py` (the catalog-opener census, 47 tests), `tests/test_docs_generated.py` (7), and this task's own census tests. They are in G5's run too; they are named here because they are the tests a split is most likely to blind (`tests/test_repo_hooks_in_sync.py` runs under G6, in the dev tree) | green, with the same test counts |
| G8 the tool | `tools/split_module.py --check <parent>` (replay), and `tools/verify_split.py <parent>` (the compiler's symbol tables, independent of the tool's scope analysis) | both exit 0 |
| G9 size | [[#r7]]'s census | green |
| G11 the derived state | `scripts/derive-digest.py` over the fixture corpus, against the golden recorded at R0 ([[#r5-digest]]) | the four legs equal the golden, after phase 1 and after every phase-2 commit |
| G10 the censuses still see | every census in the source-reader inventory, after the commit: its synthetic bypass is planted and the census **fails** on it; its allow list names no site that no longer exists ([[#r4-reproof]]) | every census fails on its bypass |
{#r4-gates}

- **The dump is deterministic, and that is tested.** The census script's first dump used
  `repr()` for parameter types and defaults; two processes over one tree gave the same 282,261
  bytes and two different hashes: 28 lines differed, each the `repr` of a `click.Path` parameter
  type, which carries the object's address (`plan29a-click-tree.log`). `tools/dump_click_tree.py` writes a type as its qualified name and
  a default as a literal or as the qualified name of its type, never a bare `repr`. A test dumps
  the tree in two child processes and compares the bytes.
- **Insertion order is not compared.** Moving a command changes the order of
  `main.commands`. The three readers of that dict in `src/` either sort it
  (`cli.py:14931`), look a key up (`:14954`, `:14956`) or build a name collection
  (`telemetry.py:1013`). R0 confirms each; G2 compares what they print in any case.
  ([[#decisions]] plan-29 D18.)
- **Tests do not change in a move commit**, except files in the source-reader inventory
  ([[#r0]] item 4), and there only: a path literal, a `module:qualname` key, or a `glob` made
  recursive. `git diff --stat <parent> <commit> -- tests/` is checked against the inventory by
  the tool's `--check`. A test that needs any other edit to pass means the move changed
  behaviour: the commit is wrong, not the test.
- **G4 is not "no name lost".** About 300 names leave `dir(refmatrix.cli)` in phase 1 by design:
  the moved callbacks and helpers that nothing outside reads. The first revision of this gate
  compared the whole attribute list and could not have passed on any move commit (ch-bsd r1
  `#b2`). What must hold is narrower and exact: what is read still resolves; what left is
  accounted for; what arrived was expected.
- **A red gate stops the phase.** The commit is not amended into green by hand. The cause is
  found; if it is a tool defect, the tool is fixed with a test and the commit is regenerated;
  if it is a real coupling the tool cannot express, it is fixed first, in its own commit.
- **A census must be shown to still see** (G10). A census keyed on a file name passes when the
  file is gone: its corpus is empty, and an empty corpus is clean. The queue review names the
  ones at risk (bug-212's `Store(` and catalog-opener census, `test_deferrals_clean`; 31 test
  files name `cli.py` or `store.py`), and one is known to be blind already
  (`test_task21_1_agent_usage_report.py:267` globs `src/refmatrix/*.py` without recursion). For
  each census in the inventory, after each commit that touches its corpus, the gate script
  plants the census's own synthetic bypass in the **new** location (a `Store(` opener inside
  `cli/catalog_cmds.py`; a deferral marker inside `store_links.py`) and requires the census to
  fail, then removes it. A census with no synthetic bypass of its own gets one in phase 0.
  ([[feedback_clean_corpus_hides_a_dead_gate]].) {#r4-reproof}
- **Commits are made in a littlebig clone; the dev tree sees one merge per phase.** A clone has
  no store and no watcher. In the dev tree every commit that touches `cli.py` is re-synced by
  the daemon, and bug-177's Stop-hook timeouts follow (queue review `#ord-7`).
- `master` is tagged `pre-split-29.5` before phase 1 merges.

### R5: `store.py` by concern {#r5}

1. `class Store(_StoreEntities, _StoreLinks, _StoreMemory, _StoreReplay, _StoreRemoval,
   _StoreRank, _StoreDerive, _StoreFragments, _StorePartition, _StoreVectors):` in `store.py`. The mixins hold methods only: no `__init__`, no class
   attributes that `Store` also defines, no state of their own. A census test checks all
   three, and checks that no method name is defined in two mixins. It takes the mixin set
   from `Store`'s bases at run time and counts the methods each defines. `Store`'s bases are
   exactly the ten mixins, and `Store.__mro__` is fixed by this task.
   - 29.2 later gives each mixin a typing host: `class _StoreVectors(_Host):`, where `_Host` is
     `refmatrix.typing_store.StoreHost` under `TYPE_CHECKING` and `object` at run time. The
     census accepts a mixin whose only base is that alias: at run time the base is `object`,
     the host is not one of `Store`'s bases, it defines no method the census can count, and the
     method resolution order is unchanged (29.2 adds an AC that it is equal before and after).
   - `src/refmatrix/typing_store.py` (29.2's leaf module: the `StoreWriter` Protocol and the
     host, declarations only) is **not** a store module for this task. It defines no mixin, so
     [[#ac-5]] does not put it in `_DERIVE_CODE_MODULES`; it is not in [[#r6]]'s store family
     (`store` and `store_*`); the size census treats it like any file.
2. `from refmatrix.store import Store` and every other name importable from `refmatrix.store`
   today still resolves there (G4). Call sites, `_DaemonWriter`, the `Store(` census and every
   test patch are unchanged: nothing outside `store*.py` can tell that the class is in several
   files. `Store.<method>` patches still work: a class attribute set
   on `Store` wins over a mixin's.
3. Mixin modules read `store.py`'s module-level names late, as `_st.<name>`, by [[#r2]]'s rule.
   That includes `time` (two tests patch `store.time`) and the derive tables.
4. **`_DERIVE_CODE_MODULES` names every file of the split.** Each phase-2 commit adds its file to
   the tuple in the same commit. `_DERIVE_PASS_MODULES` is not changed: `store.py` is in no
   pass's set today, deliberately (its comment says why), and the new files inherit that.
   - A new test asserts that every file named in either table exists beside `store.py`, and
     fails by name when one does not. Today a missing file is skipped silently.
   - The union hash changes with each phase-2 commit, as it does with any edit to `store.py`.
     `derive_pass_modules` returns the union for the no-argument callers and for every pass
     that has no entry of its own, so this is a fleet-wide `behind_code` flip with nothing
     about the derived graph changed.
   - **plan-29 D4 was decided (c)** (L106): `derive_code_hash` will hash a normalised syntax
     tree, so that annotation- and comment-only edits stop flipping it. That change is 29.2's
     (`task-29.2-mypy-gate#r7`) and lands **after** this task. It does not remove this task's
     flip: the list of modules changes here, and a move changes each file's content under any
     normalisation that is per file.
   - **So this task's release needs one announced re-stamp.** After its deploy the lead
     re-stamps each fleet store through the existing derive-stamp path, announced and backed up
     first. No store is re-derived. The evidence that nothing derived moved is item 6's digest.
     No agent re-stamps or re-derives a live store.
   - This task does not change `derive_code_hash` itself. [[#ac-5]] tests the file lists, not
     the hash function, so it holds before and after 29.2 changes the function.
   - **A module named in `_DERIVE_PASS_MODULES` is not split in this task** ([[#r7]], criterion
     6), so that table is not changed here, as this item has said from the start.
5. `__qualname__` changes for moved methods (`Store.x` → `_StoreFragments.x`). The catalog-opener
   census keys on it; its allow list is re-keyed in the commit that moves the method (source
   inventory rule, [[#r4]]). R0 lists any other reader of `__qualname__` or `__module__`
   (none in `cli.py` or `store.py` at `f3709d2`).
6. **The derived state is shown not to have moved** (asked by 29.2's author after L106; the
   lead names this digest as the evidence for the re-stamp). {#r5-digest}
   - The tool, the corpus and the test are the ones `task-29.2-mypy-gate#derive-digest`
     specifies (`scripts/derive-digest.py`, `tests/fixtures/derive_digest/`,
     `tests/test_derive_digest_unchanged.py`; four legs: graph, vectors, PageRank prior, memory
     compile; every pass shown to have run; a changed corpus that must differ leg by leg). This
     task builds them **first**, in phase 0, to that specification, because the golden has to
     exist before the first store move. `ch-test-engineer` commits the tool, the corpus and
     `golden.json`, recorded on the `pre-split-29.5` tree.
   - **Gate G11:** the four legs equal the golden after phase 1's last commit and after **every**
     phase-2 commit. A leg that differs stops the phase like any red gate.
   - The golden names its commit, the embed model id and the duckdb version. It is recorded
     after the dev venv is on duckdb 1.5.3 (`plan-review-fable-store D5`, decided).
   - 29.2 and 29.3 then only check that the same golden is still green
     (`task-29.3-converge-shapes#k-r6`).

### R6: private names used across modules {#r6}

After the moves, every `src` → `src` use of another module's `_name` is listed and resolved.

- **What counts:** a `_`-prefixed name (not dunder) taken from a different `refmatrix` module
  by import or by attribute. **Package-internal access does not count:** `cli/*_cmds.py`
  reading `_cli._root` is inside the package `refmatrix.cli`, and `store_*.py` reading `_st._X`
  is inside the store module family (the family is named in the census: `store` and
  `store_*`). That is what the underscore means there.
- **The list** is a table in the summary: user file, target module, name, and the outcome.
  At `f3709d2` it has 55 rows (76 sites). For a `cli` helper the table has one more column:
  **logic or adapter** (does the function decide something, or only parse and print?). 24.2a's
  "hook paths become verbs" starts from the rows marked logic. The three names `handoff` takes
  from `cli` are declared exceptions ([[#r2b]]) and are rows of this table with the outcome
  "declared; owner <task>". Each other row ends as one of:
  - **public:** the name loses its underscore and is the module's API, with a docstring that
    says who uses it. Tests that named it are re-pointed by `ch-test-engineer`, in a commit of
    their own **before** the rename: that commit is the RED (the tests name a public symbol that
    does not exist yet), and the implementer's rename is the GREEN. The implementer edits no
    test ([[tdd-governance]]);
  - **moved:** the function belongs to the user's layer, or to a third module both can import,
    and its body reads no name that tests patch on its old module ([[#r2b]] shows the check; a
    function that fails it is declared, with an owner, and not moved);
  - **removed:** the use is dead or duplicated.
- **A census test** (`tests/test_private_cross_module_census.py`) scans `src/` with `rglob` and
  fails on any such use. When this task ends its allow list holds only the three names of the
  declared `handoff` exception, with the same owner.
- Phase 3 commits are not tool moves. Each is an ordinary change: the census's must-fail case
  first, then the rename or move, then G5 around it. Tests → `src` private uses (742 sites)
  are not in scope; they are counted in the summary.

### This task's censuses, and how each reads the code {#censuses}

29.3's slice K moves every census that walks `src/refmatrix` with `ast` onto one kit
(`task-29.3-converge-shapes#k-r7`), keeping its allow list and its synthetic bypass. So that
the list is not guessed:

| Census | Test file | Reads | Moves onto the kit |
|---|---|---|---|
| import layering ([[#ac-13]]) | `tests/test_import_layering_census.py` | `ast` over `src/refmatrix` | yes; both allow-list entries and the "owner must resolve" must-fail are kept |
| private names across modules ([[#ac-6]]) | `tests/test_private_cross_module_census.py` | `ast` over `src/refmatrix` | yes |
| patch surface ([[#ac-3]]) | `tests/test_cli_patch_surface.py` | `ast` over `tests/` (patch targets) and over `src/refmatrix/cli/` and `store_*.py` (bindings, `global`) | yes |
| mixins ([[#r5]] item 1) | `tests/test_derive_tables_name_real_files.py` (with AC-5) | run-time introspection of `Store`'s bases; no `ast` walk | no |
| module names ([[#ac-4]]) | `tests/test_cli_entry_points.py` | file stems against `sys.stdlib_module_names`; no `ast` | no |
| derive tables ([[#ac-5]]) | `tests/test_derive_tables_name_real_files.py` | two tuples and the file system | no |
| module size ([[#ac-7]]) | `tests/test_module_size_census.py` | line counts | no |
{#censuses-table}

### R7: the size ceiling {#r7}

`tests/test_module_size_census.py`: no `src/refmatrix/**/*.py` is over **3,000 lines**, except
entries in `tools/module_size_exceptions.json` (file, lines when listed, reason, the
assessment's anchor, owner task). An excepted file may not grow past its listed size. A new
file gets no exception.

- **No module produced by the split is over the ceiling.** After phase 2, `cli/*` and
  `store*.py` hold no exception, whatever the assessments below conclude.
- **`daemon.py` (7,355), `verbs.py` (3,653), `ingest.py` (3,144)** are over the ceiling and are
  not `cli` or `store`. The plan says `daemon.py` "is assessed after, not split by default",
  and its acceptance says "no module over the size target". How to read the two together was
  plan-29 D17. **The user decided it on 2026-11-14 (ruling L106): the default below, with a
  sixth criterion.**
- **The rule:** each of the three gets a
  written assessment in the summary, by the fixed criteria below, and then either a split in
  this task by the same tool and gates (a phase 2b, after `store`), or an exception row with a
  named owner task.
- **The criteria** (all must hold to split here):
  1. a seam exists that the tool can cut: registered functions (`daemon.py`'s 89 `_op_*`
     functions, 2,339 lines; `verbs.py`'s verb registry) or a per-method map of one class;
  2. the patch inventory for the module leaves every patched name in the origin module
     (tests patch `daemon` attributes at 248 sites, 23 names; `verbs` at 61, 18);
  3. no move commit needs a test edit outside the source-reader rule;
  4. the result is under the ceiling. For `daemon.py` that takes both the ops (2,339) and the
     `Daemon` class (2,668 lines, 70 methods), since removing the ops alone leaves 5,016;
  5. no approved, unbuilt spec is about to rewrite the seam (23.x and 18.x add to `daemon.py`;
     16.5 guts the grep block, which is why that block moves as one module and is not cut);
  6. **the module is not named in `_DERIVE_PASS_MODULES`.** A derive-pass module is not split
     in this task. Splitting one changes that table, and flips its passes to `behind_code` on
     every fleet store, in a release that plan-29 D4 does not cover (ch-bsd r1 `#s2`, as
     extended; the lead's ruling).
- **What the criteria already settle at `f3709d2`:**
  - `ingest.py` fails criterion 6: it is the whole module set of the `ingest` and `semantic`
    passes. It is **not split** here. It gets its assessment and an exception row.
  - `daemon.py` fails criterion 5 while 23.x and 18.x are unbuilt. It is **not split** here.
  - `verbs.py` is the only one of the three that can be split in this task, in a phase 2b,
    and only if its assessment passes criteria 1 to 5.
- **What each assessment records,** whatever it concludes:

  | Module | Recorded |
  |---|---|
  | `daemon.py` | the two seams and their sizes; the patch surface; every census that keys on `_op_*`; which approved specs add to it |
  | `verbs.py` | the registry seam; the patch surface; that every 0.83.0 merge conflicted in it |
  | `ingest.py` | that it is 5% over; that criterion 6 keeps it whole in this task; what a later split would have to do about `_DERIVE_PASS_MODULES` |
  {#r7-assessed}

- The assessments are written after phase 2, on the tree the split leaves: the tool, the gates
  and the patch-surface method are what any further split would reuse.

### R8: the symbol map, the citation tool, and the hand-off to 29.6 {#r8}

**This task publishes the map and builds the tool. The rewriting pass is task 29.6**
([[task-29.6-citation-and-pin-repoint]]), which runs after 29.2 and 29.3. Lines move again in
those two tasks, and 29.3 renames helpers; a pass run now would be run twice (queue review
`#p29-3`). The first revision of this section handed the pass to "the plan's closing step",
which was a hand-off to nothing (ch-bsd r1 `#b3`).

1. **The map.** `docs/architecture/module-split-map.md` (GMD, generated by the tool from the
   two map files and from phase 0b's and phase 3's moves) has one row per moved top-level
   class and function and per moved `Store` method: **symbol, old module, new module**. The
   same table is in the summary, and `tools/split_maps/symbol_map.json` is its machine-readable
   form. `docs/architecture/ARCHITECTURE_INDEX.md` links it. 29.2 derives its strict mypy set
   from it, and 29.3 its module lists and census allow lists ([[#ac-11]]).
2. **The tool.** `tools/repoint_citations.py` rewrites `cli.py:NNNN` and `store.py:NNNN` in a
   spec. For each site it takes the spec's last-change sha, finds the def that held line NNNN
   in the module **at that sha**, and writes the def's home as `` `cli/<module>.py::<def>` `` or
   `` `store_<concern>.py::Store.<method>` ``, the `module.py::symbol` form that
   `docs/architecture/todo.md` G12 already uses.
   - A site whose line was module-level code, or whose def no longer exists, is not guessed. It
     is listed with the spec and the old text.
   - It also lists, without rewriting, every **pin**: a qualified name (`cli.compact`,
     `store.Store.rebuild_entities_indexes`), an AST scope keyed on the file `store.py` or
     `cli.py`, or a non-recursive `src/refmatrix/*.py` walk ([[#r0]] item 11). A pin is a
     requirement, not a citation.
3. **In this task:** the tool is built and tested ([[#ac-8]]), and run in dry-run mode on the
   merged tree. The summary gives, per spec, the count that resolves, the unresolved sites and
   the pins. That dry run is 29.6's first input.
4. **What 29.6 owns**, so that nothing is left to "later": the 271 citations in 44
   not-completed specs (re-counted at its base); the pins in 18.2, 18.3, 22.1a, 22.2, 22.6,
   16.6 and bug-218; 26.5's `daemon.py:3376` site; 21.2's three gold files that are `cli.py` or
   `store.py`; the 21 line citations in `docs/`.
5. **Between this task's merge and 29.6**, every such citation and pin names a file that is not
   there. That window is real and is stated, not hidden: the lead's window announcement
   ([[#r9]]) says so; no task that builds from one of those specs starts before 29.6, or it
   resolves its own citations first by T0's R0.1 rule, using the map.
6. **History is not rewritten**, here or in 29.6. Completed specs, handoffs, summaries and the
   ledger keep their citations (759 + 394 sites). The map resolves them.

### R9: the window {#r9}

This task changes where 25,000 lines live. Any branch that edits those lines while it runs
cannot be merged afterwards without redoing its work by hand.

1. **Before phase 1**, in the dev repository:
   - `git branch --no-merged master` lists no branch whose diff from `master` touches
     `src/refmatrix/cli.py` or `store.py`, or each one that does is declared dead in the
     window's announcement (one at `f3709d2`: `feat/intuition-lance`);
   - for each `/Volumes/littlebig/refmatrix-*` clone (a one-level listing, no search):
     `git status --porcelain` and `git log master..HEAD` show nothing on those two files;
   - plan-29 29.2 and 29.3 have not started ([[plan-29-code-quality#order]]).
2. **The lead announces** the window in `handoff.md` and on the bus, with its expected length,
   and dispatches no `src/` work until it closes. Spec, doc and measurement work continues.
3. **Phases 1 and 2 are two windows or one**, at the lead's choice. `store.py` work may resume
   between them only if phase 2 has not started.
   - **Nothing that edits the two modules may be in flight.** The store review lists the tasks
     that rebase onto this one and may not run beside it: bug-185, 23.1, 23.3, 16.6, 17.1,
     17.4, 22.1a, 22.2, 22.6, bug-218, D-Q1, 16.1, 16.5, 28.1. Independent of it, and free to
     run in the measurement lane: 23.4, the fold evaluation, 28.2-28.4, 16.2-16.4, 22.5.
4. **Each phase's merge into the dev tree is a user-gated store event** ([[#r9-store-event]]).
5. **Deploy** is the lead's, from a committed `master` sha, after a phase's merge. The deploy
   note carries: R0 item 8's answer and plan-29 D4's; that `~/refmatrix/src/refmatrix/cli.py`
   must be absent after the fast-forward; the smoke checks (`rmx version -v`,
   `python -m refmatrix.cli version` in the deploy venv, a daemon restart and status, an MCP
   reconnect).
6. **The dev MCP server straddles the split.** `.mcp.json` runs `.venv-eval/bin/rmx mcp`: a
   long-lived process on dev code. After a phase merges it still holds the old modules, and its
   next lazy `from refmatrix.cli import …` meets the new layout. The announcement tells every
   session on the dev tree to `/mcp` reconnect after each phase's merge.
7. **Released alone, with its own go, and one announced re-stamp.** One release holds this
   task's code and nothing else, so that a regression after it has one suspect.
   - **Its own go.** The user's standing go for plan-29 releases (`plan-review-fable D4`,
     decided, L106) excludes a release that changes the store on disk. This one does, twice:
     the store event at the merge, and the derive-hash flip from the changed module list. It
     stays a per-release go.
   - **One re-stamp** after the deploy, by the lead, as [[#r5]] item 4 says, with G11's equal
     digest as its evidence. 29.2 and 29.3's later release is separate and has its own
     (`task-29.2-mypy-gate#d4`).
8. **No install window.** Nothing in this task may make `rmx install-hooks --check` report drift
   on an existing install (T0's R0.7, asked of all five plan-29 tasks). The hook generators
   import nothing from `cli`; R0 confirms it, and G7's run in the dev tree shows it.
9. **The window closes** when the phase is on `master` and every clone has been told to
   re-clone or rebase.

#### The store event {#r9-store-event}

A phase's merge changes what the dev tree's live store holds. Phase 1 deletes `cli.py` from a
watched tree and adds 16 files; phase 2 rewrites `store.py` and adds 10. The daemon purges the
old paths' entities and re-ingests. Two open rows apply: bug-177 (hook timeouts during a large
post-merge sync) and **bug-107**: `purge_path` deletes the protected grep-learned rows of a
file that is deleted **or changed**, and `vacuum` then drops their evidence with no log event.
`git mv` does not carry a learned row to `cli/__init__.py`. Counting the rows and backing them
up does not keep them ([[feedback_decay_never_loses_knowledge]]; ch-bsd r1 `#s1`).

For `store.py` this is what every edit to `store.py` already does today under bug-107. For
`cli.py` it is a deletion, once.

**The steps, in this order, all the lead's** (this task's agents touch no live store):

1. **Count** (R0 item 12's query), per store and per path: learned rows, protected rows.
2. **Back up:** `scripts/backup.sh ~/refmatrix-backups/refmatrix/pre-29.5-<phase>-<sha>/`, run in
   the dev tree. It refreshes the replica, then copies the inactive catalog slot, `facts.log`
   and the `active` marker. The affected rows are also **exported in full** to
   `rows-on-cli-and-store.jsonl` in that directory (every field), so that what the store loses
   is still readable.
3. **Decide the rows, before the merge** (plan-29 D23, the user's): re-key them to their new
   paths through a store op, or accept the loss as recorded in step 2. The merge does not
   start without the answer.
4. **Take the watcher out.** The dev store's daemon is restarted without its file watcher (the
   lead's command, from `rmx daemon --help` at the deployed version; R0 writes it down). Only
   then `git merge --no-commit`.
5. **G6** (`scripts/ptest.sh --merge-gate`) runs on the merged, uncommitted tree. No watcher sees
   the tree change, and no git hook has run (there is no commit yet).
   - **Red:** `git merge --abort`. The store saw nothing. Nothing is restored, because nothing
     changed.
   - **Green:** the merge commit. Its post-commit sync is the store event, announced before the
     commit.
6. **Restore the watcher, then count again** with the same query. Both counts, the backup path
   and D23's answer go in the summary ([[#ac-15]]).
7. If D23's answer is to re-key: the op runs here, from the map's line table, and the count
   after it equals the count before.
{#r9-store-event-steps}

### R10: docs {#r10}

`docs/ARCHITECTURE.md` (the module table and the layer diagram, which name `cli.py` and
`store.py`), `docs/SYSTEM.md`, `.claude/PROJECT_PROFILE.md#layout`, `CLAUDE.md` where it names
the files, `docs/INDEX.md`, `docs/architecture/ARCHITECTURE_INDEX.md`. The 21 line citations in
`docs/` become symbols by [[#r8]]'s tool. `.claude/PROJECT_PROFILE.md` and `CLAUDE.md` are
instruction files: their edits are part of what the user approves with this plan, and the diff
is quoted in the summary. {#r10-body}

## Acceptance criteria {#acceptance}

- **AC-1: the gates can fail.** Before any move, each gate is run against a deliberate break
  made by hand on a scratch branch, and fails, naming it:
  - G1: one option's default changed; one command's help text changed; one hidden flag flipped;
    and, the other way round, two dumps of an unchanged tree from two processes are identical;
  - G2: a command registered under a second name;
  - G4: a name in the read inventory not re-exported; a moved name missing from the map; an
    attribute that appeared and is not on the expected list;
  - G5: one test made to fail with a different E line than at the parent;
  - G8: one moved function edited by hand (a renamed local variable);
  - G9: a file of 3,001 lines;
  - G10: a census whose bypass is planted in the old file name only (it must not count as seen).
  The scratch runs are logged. A gate that has only ever been run on an identical tree has not
  been shown to check anything ([[feedback_clean_corpus_hides_a_dead_gate]]). {#ac-1}
- **AC-2: every move commit passes G1-G5 and G7-G11** (G11 from phase 1's last commit on), and the summary has one row per commit:
  sha, the module moved, lines moved, each gate's result, and the two suite run names. G5's
  two runs for a commit are the commit and its parent, at the same shard count. {#ac-2}
- **AC-3: the patch still lands.** `tests/test_cli_patch_surface.py`:
  - for every name in the patch inventory: patching it on `refmatrix.cli` changes what a moved
    command sees (one generated probe per name: patch, invoke a command known to use it, assert
    the patched object was called);
  - **census, must-fail:** a synthetic command module that binds a core name with
    `from refmatrix.cli import _root` fails; one with `global _partition_override` fails;
  - **census, must-fail:** a synthetic test that patches a `refmatrix.cli` attribute that is a
    re-export (so the patch would reach nothing) fails, naming it;
  - the same three for `refmatrix.store` and the mixin modules.
  {#ac-3}
- **AC-4: the entry points work as processes.** In a child process:
  - `python -m refmatrix.cli version` exits 0 and reports this checkout; with
    `OBJC_DISABLE_INITIALIZE_FORK_SAFETY` unset it re-execs and still exits 0;
  - after the re-exec no module in `sys.modules` was loaded as a top-level name from
    `src/refmatrix/cli/`;
  - **one copy:** under `python -m refmatrix.cli`, a probe command sets module state the way
    `memory -p` does and then triggers the lazy import `handoff` makes; the lazily imported
    `refmatrix.cli` is the module the command ran in, and it sees that state. This test is
    **RED at base** (two copies, [[#fact-identity]]) and green from the rename commit on;
  - the `rmx` console script resolves `refmatrix.cli:cli_entry`.

  The naming census fails on a synthetic `cli/json.py`. `tests/test_fork_safety_reexec.py` is
  unchanged and green. {#ac-4}
- **AC-5: the derive tables name real files.** The new test fails, by name, when a table entry
  is missing on disk (must-fail: a tmp copy with one file removed). Every module that
  **defines a `Store` mixin** is in `_DERIVE_CODE_MODULES`, and a second test fails when a
  module defines one and the tuple does not name it. The rule is keyed on the mixin, not on the
  file name: a `store_*.py` that holds only a `Protocol` or type declarations (29.2's leaf
  module) is not a derive module and is not required in the tuple. {#ac-5}
- **AC-6: no private name crosses a module, except where it is declared.** The census passes on
  the tree with an allow list that holds only the three names of the declared `handoff`
  exception ([[#r2b]]), and fails on a synthetic module that imports `_x` from another
  `refmatrix` module, on one that reads `other._x` through an alias, and on one that does it
  inside a function (a lazy import). It passes on `cli/x_cmds.py` reading `_cli._root`. The
  summary's table has one outcome for each of the rows R0 listed. {#ac-6}
- **AC-7: no module produced by the split is over 3,000 lines.** The size census is green;
  `cli/*` and `store*.py` hold no exception; it fails on a 3,001-line file under `cli/` and on
  an excepted file that grew by one line. For `daemon.py`, `verbs.py` and `ingest.py`: the
  written assessment ([[#r7-assessed]]) is in the summary with each of the six criteria
  answered. `ingest.py` and every other module named in `_DERIVE_PASS_MODULES` is unchanged in
  line count by this task's move commits (a test compares the table's files at the base sha and
  at the final sha: no file was added to or removed from it). Each of the three is under the
  ceiling or has an exception row with an owner task that exists. {#ac-7}
- **AC-8: the citation tool is ready, its dry run is recorded, and 29.6 exists to use it.** On
  fixture specs the tool rewrites a line cite to the right symbol when the def moved, resolves
  the line at the spec's own sha and not at `HEAD` (a fixture where the two differ), lists a
  module-level line as unresolved without guessing, and lists a qualified-name pin and a
  non-recursive glob as pins. The dry run over `workflow/plans/` is in the summary: per spec,
  resolved, unresolved, pins. No spec is rewritten by this task: the pass is
  [[task-29.6-citation-and-pin-repoint]], whose spec exists and names this dry run as its
  input. {#ac-8}
- **AC-9: the window was real.** The summary quotes the pre-phase checks of [[#r9]] item 1 with
  their output, the announcement, and the close. {#ac-9}
- **AC-15: the store event is on the record, and nothing was lost unseen.** For each phase's
  merge the summary holds: the count query; the learned and protected row counts per store and
  per path **before** and **after**; the backup path and that `rows-on-cli-and-store.jsonl`
  holds as many rows as the before-count; plan-29 D23's answer, dated, **before** the merge
  commit's time; that the watcher was out during G6 (the daemon's own status line); and either
  "re-keyed: after = before" or "lost as recorded: N rows, listed in the export". A phase whose
  record lacks any of these is not merged. {#ac-15}
- **AC-16: the derived state did not move.** The derive digest's golden was committed by
  `ch-test-engineer` on the `pre-split-29.5` tree, before any move commit ([[#r5-digest]]). Its
  four legs equal the golden after phase 1's last commit and after every phase-2 commit (gate
  G11), and the summary gives each leg's digest at R0 and at the final sha. The check is shown
  able to fail as 29.2's section specifies: the changed corpus differs from the golden leg by
  leg. This is the evidence the lead cites for the one announced re-stamp. {#ac-16}
- **AC-10: before and after.** The [[#baseline]] tables, re-measured at the final sha, are in
  the summary beside R0's. `./scripts/lint-gmd.sh` exits 0. {#ac-10}
- **AC-11: the symbol map is published, and three names do not move.** {#ac-11}
  - The summary carries a table **symbol → old module → new module** for every moved top-level
    class and function (and every moved `Store` method). `docs/architecture/module-split-map.md`
    and `tools/split_maps/symbol_map.json` hold the same rows, and a test compares the three
    counts with the tool's.
  - `refmatrix.store.Store`, `refmatrix.query.QueryEngine` and `refmatrix.cli:cli_entry` stay
    importable under exactly those names, and a test imports each in a child process.
  - This is the AC that `task-29.2-mypy-gate` (its `#needs-295`) and
    `task-29.3-converge-shapes` cite: 29.2 derives its strict module set from the map (every
    module that now holds a symbol that lived in `verbs.py`, `query.py`, `store.py`, `handoff.py`
    or `mcp.py` at `f3709d2`), and 29.3 its memory-path module list and its `module:qualname`
    allow lists.
- **AC-12: every census still sees.** For each census in the source-reader inventory, the
  summary has a row: where its synthetic bypass was planted after the split, and the failing
  line it produced. The catalog-opener census in `tests/test_bug212_r4_red.py` is re-keyed by
  this task (`cli:_store_rw`, `cli:compact` and its `store:Store.<method>` entries get their new
  module names and nothing else), and its own "allow list names no dead site" test is green.
  29.3 relies on that test and does not re-key it. The non-recursive glob in
  `test_task21_1_agent_usage_report.py` is made recursive and shown to see a file under
  `cli/`. {#ac-12}
- **AC-13: the engine does not import the adapter, except where it is declared.** The layering
  census:
  - passes on the tree with its two-entry allow list ([[#r2b]]);
  - fails on a synthetic engine module that imports `refmatrix.cli` at module level, and on one
    that does it inside a function;
  - fails on an allow-list entry whose owner task id does not resolve, and on an entry that
    matches no import in the tree;
  - **the exceptions keep the patches:** for each patched name in [[#r2b-table]], a probe patches
    it on `refmatrix.cli`, drives the handoff path that reaches the helper, and asserts the
    patched object was called. These probes pass at base and after every phase; they are what
    would have gone silent had the helpers moved.
  {#ac-13}
- **AC-14: no hook drift.** `rmx install-hooks --check` semantics are unchanged: the generated
  hook config at the final sha equals the one at the base sha, byte for byte (the generator is
  run at both). {#ac-14}

## Test strategy {#test-strategy}

- **A move has no RED, so the gates are what is test-driven.** Phase 0 is ordinary TDD: the
  tool's tests, the dump tool's tests, the census tests and AC-3's probes are written first and
  recorded failing (the tool does not exist; the censuses' must-fail cases are RED), then made
  green. Phase 0 changes no production behaviour.
- **Characterisation tests are proven by mutation, not by a RED run.** AC-3's probes and AC-4's
  process tests pass before the split and must pass after it; a RED run at base is impossible
  by design. Each is shown able to fail by its mutation below.
- **Phases 0b and 3 are ordinary TDD** (the census's must-fail case is RED; each move or rename
  follows).
- **Mutations** (each turns a named test or gate RED within its deadline; each is reverted in
  its own command; the fix is committed before the loop; `__pycache__` is cleared after):
  1. the tool binds a core name by `from … import` in one moved function (AC-3's probe and the
     census);
  2. the tool leaves a `global _partition_override` in a moved command (AC-3);
  3. the tool drops one re-export line (G4);
  4. `cli/__main__.py` uses a relative import (AC-4's re-exec case);
  5. a command module is renamed `cli/select.py` (AC-4's naming census);
  6. `cli/__init__.py` skips importing one command module (G1: its commands are gone);
  7. one moved option's default is changed after the tool ran (G1 and G8);
  8. a `store_*.py` file is left out of `_DERIVE_CODE_MODULES` (AC-5);
  9. a mixin defines a method that another mixin also defines (R5's census);
  10. the private-name census skips function-level imports (AC-6);
  11. the size census reads only `src/refmatrix/*.py`, without recursion (G9: a 3,001-line file
      under `cli/` passes, so the test is red);
  12. `--compare` is given the same run twice (G5 is green whatever the commit did: the gate
      script must refuse two runs with one sha);
  13. the G10 script plants the bypass and does not check that the census failed (AC-12);
  14. `_subject_upsert` binds `_root` by `from … import` inside a moved copy (AC-13's probe for
      `_root` goes silent, so the probe test is red); and a third engine module gains a lazy
      `from refmatrix.cli import` (the census is red);
  15. the symbol map drops the moved `Store` methods (AC-11's count test);
  16. the tool rewrites a parameter that shadows a core name (the tool's shadow test is red,
      and `tools/verify_split.py` is red without the tool's help);
  17. `cli/__main__.py` runs the command from a second import of the package under another
      name (AC-4's one-copy probe is red);
  18. G4 treats a name missing from the map as fine (AC-1's planted break passes, so the gate's
      own test is red).
- **The suite runs before and after every phase-1 and phase-2 commit** (G5). There are 25 move
  commits (the rename, 14 command modules, 10 concern modules). Each commit's "after" is the
  next commit's "before", so that is about 26 runs: under 9 hours of machine time at 29.4's
  20-minute target, not of anyone's attention. Phases 0b and 3 add one run per commit.
- **All output to files**, through 29.4's runner, under `workflow/review-output/task-29.5/`.
{#test-strategy-list}

## Files {#files}

| File | Change |
|---|---|
| `docs/adr/0006-*.md`, `docs/adr/0000-adr-overview.md`, `docs/INDEX.md` | the layout and layering decision ([[#r1]]; authored by `ch-architect`) |
| `tools/split_module.py`, `tools/split_maps/cli.json`, `tools/split_maps/store.json`, `tools/split_maps/symbol_map.json` | new: the move tool, its maps, the published symbol map |
| `tools/dump_click_tree.py`, `tools/verify_split.py`, `tools/repoint_citations.py`, `tools/module_size_exceptions.json` | new |
| `scripts/derive-digest.py`, `tests/fixtures/derive_digest/` (corpus, changed corpus, `golden.json`), `tests/test_derive_digest_unchanged.py` | new, built in phase 0 to `task-29.2-mypy-gate#derive-digest`; 29.2 and 29.3 reuse them |
| the module R0 names as `_root_from_projects_slug`'s home | phase 0b ([[#r2b]]). `handoff.py` and `telemetry.py` are **not** changed |
| `src/refmatrix/cli.py` → `src/refmatrix/cli/__init__.py`, `cli/__main__.py`, `cli/*_cmds.py` (14) | phase 1 |
| `src/refmatrix/store.py`, `src/refmatrix/store_*.py` (10) | phase 2 |
| the modules on R6's list (24 files at `f3709d2`) | phase 3 |
| `daemon.py`, `ingest.py` | assessed, not changed ([[#r7]], criteria 5 and 6) |
| `verbs.py` | assessed; split in a phase 2b only if it passes [[#r7]]'s criteria |
| `tests/test_split_module_tool.py`, `tests/test_click_tree_dump.py`, `tests/test_cli_patch_surface.py`, `tests/test_cli_entry_points.py`, `tests/test_derive_tables_name_real_files.py`, `tests/test_private_cross_module_census.py`, `tests/test_import_layering_census.py`, `tests/test_module_size_census.py`, `tests/test_symbol_map.py`, `tests/test_repoint_citations.py` | new |
| the test files in the source-reader inventory (about 20 at `f3709d2`; the queue review counts 31 that name the two files at all) | path literals, census keys, one recursive glob; nothing else |
| `tests/tiering.py` | `ALWAYS_FILES` gains this task's census tests ([[task-29.4-suite-health#r6]]) |
| `docs/architecture/module-split-map.md`, `docs/architecture/ARCHITECTURE_INDEX.md` | new map; index row |
| `docs/ARCHITECTURE.md`, `docs/SYSTEM.md`, `.claude/PROJECT_PROFILE.md`, `CLAUDE.md` | [[#r10]] |
| `workflow/bug_registry.md` | any row the task opens or closes |
| `workflow/implementation_summaries/task-29.5-split-giant-modules.md` | new: R0, the per-commit gate table, the symbol map, R6's table, the three assessments, the citation dry run, the window record |
{#files-table}

No spec under `workflow/plans/` is edited by this task: the citation and pin pass is
[[task-29.6-citation-and-pin-repoint]] ([[#r8]]). {#files-no-specs}

## Out of scope {#out-of-scope}

- **Any behaviour change.** No bug is fixed in a move commit, including ones the move makes
  obvious. They are logged and scheduled in 29.1's grammar.
- **Splitting `daemon.py` or `ingest.py`**, and splitting `verbs.py` unless its assessment passes
  ([[#r7]]; plan-29 D17, decided).
- **Decomposing `Store`** into collaborating objects ([[#r1]]).
- **Moving the core out of `cli/__init__.py`.** It stays where the patches expect it. Moving it
  means changing how tests reach it, which is a task about tests.
- **Re-pointing the 742 test → `src` private uses**, and typing anything: 29.2 and 29.3 land in
  the modules this task makes ([[plan-29-code-quality#order]]).
- **Rewriting any spec's citations, and revising any spec's pins:**
  [[task-29.6-citation-and-pin-repoint]].
- **Deleting dead code** ([[#r0]] item 9): its owners do that.
- **A formatter pass** over moved code. A reformat would make G8 meaningless.
- **Changing the fork-safety re-exec** ([[#fact-argv]]). Running it as `-m` would put the
  current directory first on the daemon's import path; today's form does not. That is a
  behaviour question for another task, and the naming census makes today's form safe.
- **Deciding plan-29 D23.** It is the user's.
- **Fixing bug-107.** It is open and is plan-22's; this task makes its cost at one merge visible
  and puts the choice to the user.
{#out-of-scope-list}

## The user's decisions this spec is built to {#user-decisions}

All decided on 2026-11-14 (ruling L106, [[plan-review-2026-11-13#lead]]), except the last row.

| Label | Decided | What it means here |
|---|---|---|
| plan-29 D17 | this spec's default, with a sixth criterion | [[#r7]]: no derive-pass module is split; `ingest.py` and `daemon.py` are exceptions; `verbs.py` only if its assessment passes |
| plan-29 D4 (29.2's) | (c): a normalised-AST derive hash, in 29.2, before its annotations | [[#r5]] item 4: that lands after this task, so this task's module-list change still flips the union once, and needs one announced re-stamp |
| `plan-review-fable D4` | a standing go for plan-29 releases whose suite equals the baseline by E line, the user told first, **excluding** releases that change the store on disk | [[#r9]] item 7: this task's release is excluded; it has its own go |
| `plan-review-fable-store D5` | duckdb 1.5.3 in `.venv-eval` before baselines (the lead upgrades after the 0.83.1 runs) | [[#r0]] item 13: no golden and no baseline before the upgrade |
| `plan-review-fable-memory D2` | 25.1b's `legs_ms` timing pair lands before 29.5 | [[#r0]] item 10: it is on `master` before the window opens |
| **plan-29 D23** | **open** | [[#r9-store-event]] step 3: no phase merges without it |
{#user-decisions-table}

## Decisions taken in this spec {#decisions}

- **plan-29 D16: the core stays in `cli/__init__.py`, and moved code reads it as
  `_cli.<name>`.**
  - **Why:** 191 test patches (160 of them on `_root`) and the conftest's per-test reset of
    `_partition_override` act on the module `refmatrix.cli`. With the core there and late-bound
    reads, every one of them means what it meant, with no test edited. The other shapes (a
    `_core.py` that tests are re-pointed to; names imported into each command module) either
    change 191 test sites in the same commit as the code they check, or make the patches
    silently miss.
  - **How it meets the queue review's `#b2`:** "shared helpers live in one module and are
    resolved by attribute at call time" is this, with `refmatrix.cli` itself as the one module.
    The review allows a test edit that is a patch-target rename only; this shape needs none.
  - **Cost:** `_cli.` in front of core names in moved code, and a 1,689-line `__init__.py`.
- **plan-29 D17 (decided by the user, 2026-11-14, ruling L106): what "no module over the size
  target" means for `daemon.py`, `verbs.py` and `ingest.py`.**
  - **The conflict was:** the plan's 29.5 text splits `cli.py` and `store.py` and says `daemon.py`
    "is assessed after, not split by default"; its acceptance says "no `src/refmatrix` module
    over the size target". `daemon.py` is 7,355 lines, `verbs.py` 3,653, `ingest.py` 3,144.
  - **Decided:** this spec's default, with a sixth criterion. Assess all three by [[#r7]]'s six
    criteria; split in this task the ones that pass; the others get a dated exception with an
    owner task, and the size census holds them at their current size. **No module named in
    `_DERIVE_PASS_MODULES` is split in 29.5.**
  - **What that comes to:** `ingest.py` cannot pass (criterion 6) and `daemon.py` does not pass
    while 23.x and 18.x are unbuilt (criterion 5). So the decision and the queue review's
    reading (`#b1`: all three are assessed exceptions) coincide, unless `verbs.py`'s assessment
    passes; then `verbs.py` alone is split here, in a phase 2b.
  - The alternatives that were not taken: (a) split all three in 29.5 whatever the criteria
    say; (b) split none and decide later.
- **plan-29 D23 (open, for the user): the learned and protected rows keyed on `cli.py` and
  `store.py` when a phase merges.**
  - **What happens with no decision:** bug-107. The rows are purged with the path, and their
    evidence is vacuumed.
  - **(a) Accept the loss, recorded.** Every affected row is exported in full and backed up
    first; the count before and after is in the summary; grep re-learns what is asked for
    again. No new code. What is lost is whatever a row carries that grep cannot re-derive (R0
    item 12 says what that is and how many rows have it).
  - **(b) Re-key through a store op.** The move tool knows, for every moved line, its new file
    and line. A daemon op re-keys each learned row from that table, and the after-count equals
    the before-count. This is new write surface: it needs its own small spec and its own
    review before the merge, and it delays phase 1.
  - **(c) Fix bug-107 first** (22.6 R4 keeps learned rows on any edit), then merge. That
    reorders the queue: plan-22 is step thirteen of the queue review's recommended order.
  - **Pending default:** none that merges. With no answer, [[#r9-store-event]] step 3 holds the
    merge. If R0 item 12 counts **zero** rows on both paths in every store, there is nothing to
    decide and the record says so.
  - **Why the user's:** it is knowledge on the live store, and the user's rule is that removal
    goes only through an audited path.
- **plan-29 D18: the click tree is compared as a sorted structural dump plus the help output,
  not by the insertion order of `main.commands`.**
  - **Why:** the order necessarily changes when registration moves between files, and no
    reader depends on it (three readers, each sorted or keyed). Restoring the order by code
    would be new behaviour written only to satisfy a gate.
- **plan-29 D19: `Store` is composed from mixins in flat sibling modules; `store` does not
  become a package.**
  - **Why:** `refmatrix.store` stays a module with the same `__file__`, so the 15 module-level
    patches, the 27 path literals and the derive hash's "beside `store.__file__`" rule keep
    working. Method bodies move verbatim (`self.` calls are unaffected; there is no name
    mangling and no `super()` to break). The queue review's `#b1` reached the same shape
    independently.
  - **Cost:** `Store`'s method resolution order is now part of the design; R5's census keeps the
    mixins from overlapping.
- **plan-29 D21: the store is cut by method, into ten concern modules, not by the file's
  banners into the plan's four.**
  - **Why:** the banners misplace the four largest methods ([[#map-store]]), and the store
    review showed that evidence/links and replay, where six approved specs land, had no home in
    the plan's list.
- **plan-29 D22: the citation and pin pass is its own task, 29.6, after 29.2 and 29.3.**
  - **Why:** a spec re-pointed now is re-pointed again after 29.3 renames helpers. Ruling L105
    made the pass a task with a spec, so that the hand-off has a receiver.
- **plan-29 D24: a `-m refmatrix.cli` process has one copy of the CLI after the split, and
  that is accepted.**
  - **What changes:** today such a process has two ([[#fact-identity]]): the commands run in
    `__main__`, and `handoff`'s lazy import gets a second copy whose `_partition_override` is
    unset. After the split it has one, as every `rmx …` process already does.
  - **Why accepted and not preserved:** keeping two copies would mean importing the package a
    second time under another name on purpose. The console-script path, which is what the
    deployed `rmx`, the hooks and the launchd daemons run, already has one copy, so the change
    makes the four `-m` spawn sites behave like everything else.
  - **Guard:** R0 item 5 lists every outcome that differs today between the two forms. If one
    of them is relied on by a production spawn site, the task stops and raises it before phase
    1. The ADR records the change. [[#ac-4]] probes it in a child process.
  - **This is the one behaviour change in a task whose rule is none.** It is named here so it
    is not found later.
- **Not decided here, because the plan or the reviews decided it:** `cli` becomes a package, one
  module per command group; moves only; one group per commit; the ceiling is about 3,000 lines
  for every module the split produces; mixins; the ADR; a published symbol map; every census
  re-proven on its bypass.
{#decisions-list}

## Revision note (2026-11-14) {#rev-note}

Revised the same day for three plan reviews (queue, store, memory) and for the sibling specs
29.2 and 29.3. Changed: the store map is by method, with `store_links.py` and `store_replay.py`
named; the cli map reserves `grep`, `vectors`, `catalog`, `learn` and `removal` modules; phase
0b ([[#r2b]]) and the layering census are new; G10 and [[#ac-12]] (every census re-proven) are
new; [[#ac-11]] (the symbol map and three stable names) is new, for 29.2 and 29.3; [[#r7]]
states the split's own ceiling as the review does, and keeps plan-29 D17 open for the user with
its pending default (the review's reading is recorded as alternative (b); the user has since
decided it, see [[#rev-note-3]]); [[#r8]] publishes the map and the tool
here and hands the rewriting pass to the plan's end; [[#r9]] gains the MCP reconnect, the
release-alone rule and the no-drift rule; the baseline is 29.4's stage 5. {#rev-note-body}

## Revision note 2 (2026-11-14, after ch-bsd r1 and ruling L105) {#rev-note-2}

ch-bsd reviewed `dba9afd` and found 3 BULLSHIT, 8 SKETCHY and 12 MEH across the five plan-29
specs (`bsd-plan29-spec-r1`, dev `master` `549458e`). Ruling L105 decided how each is fixed.
This spec's share:

| Finding | Change here |
|---|---|
| B1: phase 0b moved helpers whose bodies read test-patched `cli` names | [[#r2b]]: the three `handoff` helpers and `telemetry`'s read of `main` stay and are declared exceptions with an owner; only `_root_from_projects_slug` moves; [[#ac-13]] with probes that the patches still land; [[#ac-6]] |
| B2: gate G4 could not pass | [[#r4-gates]] G4 is three exact checks; AC-1's planted break removes a read name |
| B3: the citation and pin pass had no task | [[#r8]] hands it to [[task-29.6-citation-and-pin-repoint]]; [[#ac-8]]; plan-29 D22 |
| S1: the merge is a lossy store event | [[#r9-store-event]], R0 item 12, [[#ac-15]], gate G6 with the watcher out, plan-29 D23 (open) |
| S2: the derive-hash flip and plan-29 D4 did not meet | [[#r5]] item 4, [[#r9]] item 7, [[#user-decisions]] |
| S5: module identity under `-m` | [[#fact-identity]], R0 item 5, [[#ac-4]] (RED at base), plan-29 D24 |
| S6: no rule for references between command modules | [[#r2]] items 9 and 10, [[#r3]] (shadowing tests; `tools/verify_split.py` from the compiler's symbol tables), gate G8 |
| M4: two wrong numbers | [[#baseline-reach]]: 4 `global` statements; 4 spawn sites in 3 files |
| M6: seams with 29.2 | [[#ac-5]] keys on the mixin, not the file name; [[#r5]] item 1 says what the mixin census counts |
| M9: a GREEN commit that edits tests | [[#r6]]: `ch-test-engineer` re-points first, as the RED |
{#rev-note-2-table}

## Revision note 3 (2026-11-14, after ruling L106 and the 29.2 / 29.3 seams) {#rev-note-3}

- **plan-29 D17 is decided** (L106): this spec's default with a sixth criterion, no
  derive-pass module split ([[#r7]], [[#ac-7]], [[#decisions]]). ch-bsd's extension of S2 is
  met by that criterion.
- **plan-29 D4 = (c), `plan-review-fable D4` and `plan-review-fable-store D5` are decided**
  ([[#user-decisions]]): one announced re-stamp after this task's release ([[#r5]] item 4); a
  per-release go ([[#r9]] item 7).
- **The derive digest is recorded here** ([[#r5-digest]], gate G11), at R0, to 29.2's
  specification, so that it is evidence for this task's re-stamp.
- **B1 is said plainly** ([[#r2b-stay]]) and its owner is confirmed:
  `task-29.3-converge-shapes#slice-h`.
- **Seams with 29.2** ([[#r5]] item 1): `typing_store.py` is not a store module; a
  `TYPE_CHECKING`-only host does not count as a base. [[#censuses]] lists which censuses 29.3's
  kit takes.
- **plan-29 D23 is still open.**
{#rev-note-3-list}
