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
> **Open user decisions this task waits on and does not settle** ([[#open-decisions]]):
> `plan-review-fable D4` (who says go for its release), `plan-review-fable-store D5` (the dev
> venv's duckdb, before any baseline).
> User gates: the window's start (the lead announces it; the user may hold it), and one open
> decision of this spec's own, **plan-29 D17** ([[#decisions]]), which the lead puts to the user.

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
| `python -m refmatrix.cli` spawn sites | 7 in `src/` (6 files, among them `daemon.py:7059`, `scheduler.py:131`, `ui/server.py:191` and `:578`); 22 in tests (8 files) |
| `src` modules that import from `cli` | 2: `handoff.py` (three private names, lazily, "cli->handoff cycle") and `telemetry.py` (`main`) |
| `global` statements in `cli.py` | 5: `_partition_override` × 4, `file` × 1 |
{#baseline-reach-table}

The queue review counted the same surface by grep: 185 `monkeypatch.setattr(cli, …)` sites in
64 files (159 on `_root`) and 49 private names. The counts here are from the syntax tree, and
include string targets and `mock.patch`: 191 and 45. The two agree on what matters. R0's
inventory is the list that binds. {#baseline-reach-two-counts}

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

### Three facts that decide the design {#baseline-facts}

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
5. **The argv inventory:** every reader of `sys.argv[0]` and every place a command line is
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
    pair, if the user's answers to the reviews' decisions put them before the split. R0 lists
    each as merged or as explicitly held until after.
11. **The pins other specs hold on these files** ([[#r8]]): every unbuilt spec that walks
    `src/refmatrix/*.py` without recursion, or exempts a site by a qualified name such as
    `cli.compact` or `store.Store.rebuild_entities_indexes`, or keys an AST check on the file
    `store.py` or `cli.py`. The store review names the known ones: 18.2 R11/R13/AC-17, 18.3
    AC-14, 22.1a AC-8c, 22.2, 22.6 AC-6f, 16.6 AC-9c/9d/AC-12, bug-218 AC-2/AC-4b.
12. **Baselines wait for `plan-review-fable-store D5`.** No gate golden and no suite baseline is
    generated on the dev venv's duckdb 1.5.2 if the decision is to raise it.

### R1: the decision is recorded first {#r1}

`ch-architect` authors the next ADR in `docs/adr/` (0006 at `f3709d2`), "module layout and
import layering", through `/ch-crucible`, before the first move commit, with a row in
`docs/adr/0000-adr-overview.md` and `docs/INDEX.md`. It records:

- **This is a file-size split, not a decomposition.** `Store` is still one class with one
  namespace and one lock; its methods live in several files. Composition (a `Store` made of
  collaborating objects) is a later decision, which 29.2's writer `Protocol` informs. The split
  must not be read as that decision, and must not make it harder.
- **The layering:** `cli` → `verbs` → the engine. The engine never imports `cli`. A function
  the engine calls does not live in the CLI package ([[#r2b]]). An import census enforces it.
- **The package rule:** a core that is read late by attribute ([[#r2]]); what `_name` means
  inside a package and across packages ([[#r6]]).
- **The ceiling** and its exception list ([[#r7]]), as plan-29 D17 is answered.

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
5. **A name tests read stays reachable.** For each name in the read inventory that moves, the
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
   that it also runs as a script after the re-exec. The re-exec itself is not changed.

### R2b: what the engine calls moves down first {#r2b}

A function that code outside the CLI package calls is not a CLI function. It moves **down** to
the layer that owns it, before the split, and never into `cli/<area>_cmds.py`.

- **Known at `f3709d2`:**
  - `handoff.py:669` and `:699` lazy-import `_sync_memory_dir`, `_subject_link` and
    `_subject_upsert` from `cli` ("lazy: cli->handoff cycle"). The save-state engine calls the
    adapter.
  - `telemetry.py:1011` imports `main` from `cli` to list the commands.
  - `_root_from_projects_slug` is called only inside `cli.py` today, and 26.5 needs it from the
    engine (memory review `#p29-5`).
- **Each moves in its own commit, in phase 0b, as an ordinary change:** a RED test that the
  engine module imports nothing from `refmatrix.cli`; then the move to the owning module
  (`handoff`, the memory bridge, `discovery`: R0 names each home and says why); `cli` keeps a
  name bound to the same object, so the read inventory and every test are unchanged; G5 around
  the commit.
- **The census:** `tests/test_import_layering_census.py` fails on any import of `refmatrix.cli`,
  at module level or inside a function, from a `src/refmatrix` module outside the package. Its
  allow list is empty after phase 0b. `telemetry`'s need (the command names) is met by the CLI
  handing the list in, not by the engine reaching up.
- This is done before the tool runs, so the tool never moves an engine function into a command
  module and then has it moved again.
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

**Order.** Phase 0 builds the gates. Phase 0b moves down what the engine calls. Phase 1 is
`cli`. Phase 2 is `store`. Phase 3 is the private names. Each commit lands on the task branch; the branch merges to `master` once, at
the end of a phase.

| Phase | Commits |
|---|---|
| 0 | the tool and its tests; the gates and goldens of this section, generated at the base sha and committed; the inventories of [[#r0]] |
| 0b | [[#r2b]]: one commit per function the engine calls, moved down. Ordinary changes, not tool moves |
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
| G4 the surfaces | for `refmatrix.cli` and `refmatrix.store`: the sorted list of public and private attribute names, each with its kind (function, class, module, other) | no name lost; additions are only `_cli`-style module aliases the tool lists |
| G5 the suite | `scripts/ptest.sh --tier all` at the parent and at the commit, then `--compare` ([[task-29.4-suite-health#r2]]) | equal by (node id, phase, E line), collected counts equal |
| G6 the dev tree | `scripts/ptest.sh --merge-gate` on the merged dev tree before each phase's merge commit ([[task-29.4-suite-health#r7]]) | passes |
| G7 parity and censuses | `tests/test_verb_parity.py` (167 tests), `tests/test_bug212_r4_red.py` (the catalog-opener census, 47 tests), `tests/test_docs_generated.py` (7), and this task's own census tests. They are in G5's run too; they are named here because they are the tests a split is most likely to blind (`tests/test_repo_hooks_in_sync.py` runs under G6, in the dev tree) | green, with the same test counts |
| G8 the tool | `tools/split_module.py --check <parent>` | exit 0 |
| G9 size | [[#r7]]'s census | green |
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
   three, and checks that no method name is defined in two mixins.
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
     What the fleet shows when it does is R0 item 8, and it goes in the deploy note.
5. `__qualname__` changes for moved methods (`Store.x` → `_StoreFragments.x`). The catalog-opener
   census keys on it; its allow list is re-keyed in the commit that moves the method (source
   inventory rule, [[#r4]]). R0 lists any other reader of `__qualname__` or `__module__`
   (none in `cli.py` or `store.py` at `f3709d2`).

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
  from `cli` are already gone by phase 0b ([[#r2b]]). Each remaining row ends as one of:
  - **public:** the name loses its underscore and is the module's API, with a docstring that
    says who uses it. Tests that named it are re-pointed in the same commit;
  - **moved:** the function belongs to the user's layer, or to a third module both can import
    (`handoff.py` takes three names from `cli` through a lazy import that exists only to dodge
    an import cycle; a function that the handoff engine needs is not a CLI function);
  - **removed:** the use is dead or duplicated.
- **A census test** (`tests/test_private_cross_module_census.py`) scans `src/` with `rglob` and
  fails on any such use. Its allow list is empty when this task ends.
- Phase 3 commits are not tool moves. Each is an ordinary change: the census's must-fail case
  first, then the rename or move, then G5 around it. Tests → `src` private uses (742 sites)
  are not in scope; they are counted in the summary.

### R7: the size ceiling {#r7}

`tests/test_module_size_census.py`: no `src/refmatrix/**/*.py` is over **3,000 lines**, except
entries in `tools/module_size_exceptions.json` (file, lines when listed, reason, the
assessment's anchor, owner task). An excepted file may not grow past its listed size. A new
file gets no exception.

- **No module produced by the split is over the ceiling.** After phase 2, `cli/*` and
  `store*.py` hold no exception. This much is the same under every answer to plan-29 D17.
- **`daemon.py` (7,355), `verbs.py` (3,653), `ingest.py` (3,144)** are over the ceiling and are
  not `cli` or `store`. The plan says `daemon.py` "is assessed after, not split by default",
  and its acceptance says "no module over the size target". **How to read the two together is
  plan-29 D17, open, and the user's** ([[#decisions]]).
- **The pending default, built unless the user answers otherwise:** each of the three gets a
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
     16.5 guts the grep block, which is why that block moves as one module and is not cut).
- **What each assessment records,** whatever it concludes:

  | Module | Recorded |
  |---|---|
  | `daemon.py` | the two seams and their sizes; the patch surface; every census that keys on `_op_*`; which approved specs add to it |
  | `verbs.py` | the registry seam; the patch surface; that every 0.83.0 merge conflicted in it |
  | `ingest.py` | that it is 5% over; that it is in the derive pass sets, so any edit to it flips fleet stores to `behind_code` |
  {#r7-assessed}

- The assessments are written after phase 2, on the tree the split leaves: the tool, the gates
  and the patch-surface method are what any further split would reuse.

### R8: the symbol map, and specs that cite a line {#r8}

**This task publishes the map and builds the tool. The rewriting pass runs once, after 29.2
and 29.3.** Lines move again in those two tasks, and 29.3 renames helpers; a pass run now would
be run twice (queue review `#p29-3`).

1. **The map.** `docs/architecture/module-split-map.md` (GMD, generated by the tool from the
   two map files and from phase 0b's and phase 3's moves) has one row per moved top-level
   class and function and per moved `Store` method: **symbol, old module, new module**. The
   same table is in the summary, and `tools/split_maps/symbol_map.json` is its machine-readable
   form. `docs/architecture/ARCHITECTURE_INDEX.md` links it. 29.2 derives its strict mypy set
   from it, and 29.3 its module lists and census allow lists ([[#ac-11]]).
2. **The tool.** `tools/repoint_citations.py` rewrites `cli.py:NNNN` and `store.py:NNNN` in
   every spec under `workflow/plans/` whose `metadata.status` is not completed. For each site it
   takes the spec's last-change sha, finds the def that held line NNNN in the module **at that
   sha**, and writes the def's home as `` `cli/<module>.py::<def>` `` or
   `` `store_<concern>.py::Store.<method>` ``, the `module.py::symbol` form that
   `docs/architecture/todo.md` G12 already uses. A symbol does not rot when lines move; T0's
   R0.1 already found `store.py:717` at `:1159`.
   - A site whose line was module-level code, or whose def no longer exists, is not guessed. It
     is listed with the spec and the old text.
   - It also lists, without rewriting, every **pin**: a qualified name (`cli.compact`,
     `store.Store.rebuild_entities_indexes`), an AST scope keyed on the file `store.py` or
     `cli.py`, or a non-recursive `src/refmatrix/*.py` walk ([[#r0]] item 11). A pin is a
     requirement, not a citation.
3. **In this task:** the tool runs in dry-run mode on the merged tree. The summary gives the
   count that resolves, the unresolved sites, and the pins, per spec.
4. **The pass** is plan-29's closing step, after 29.3 and 29.2. Its rules, from the reviews:
   - a cite-only rewrite needs no ch-bsd re-approval;
   - a spec whose **requirement** depends on location gets its owner's freshness check (26.5's
     "wrap `run` at `daemon.py:3376`"; 23.1's 33 `store.py` sites; every pin). A pin is
     rewritten to "every module under `src/refmatrix`, recursive", located by symbol;
   - T0's R0.1 (re-verify every cited site at the branch base) is the rule for every task that
     builds from a spec afterwards.
   This spec hands the pass to the plan: the lead adds it to
   [[plan-29-code-quality#order]] as a step with an owner.
5. **History is not rewritten.** Completed specs, handoffs, summaries and the ledger keep their
   citations (759 + 394 sites). The map resolves them.
6. **Frozen gold that names the files.** 21.2's nine gold files include three that are `cli.py`
   or `store.py` (memory review `#s31`). They are keyed on the unique definition or re-frozen
   after this task, by 21.2's owner; the summary lists them with the pins.

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
4. **The merge to the dev tree is announced as a store event.** It deletes `cli.py` from a
   watched tree and adds eleven files; the live store's daemon purges the old path's entities and
   re-ingests. bug-177 (hook timeouts during a large post-merge sync) and bug-107 (learned rows
   deleted with a purged path) both apply. The lead counts the learned rows on `cli.py` and
   `store.py` before the merge and backs up first; this task's agents do not touch the store.
5. **Deploy** is the lead's, from a committed `master` sha, after a phase's merge. The deploy
   note carries: R0 item 8's answer; that `~/refmatrix/src/refmatrix/cli.py` must be absent
   after the fast-forward; the smoke checks (`rmx version -v`, `python -m refmatrix.cli version`
   in the deploy venv, a daemon restart and status, an MCP reconnect).
6. **The dev MCP server straddles the split.** `.mcp.json` runs `.venv-eval/bin/rmx mcp`: a
   long-lived process on dev code. After a phase merges it still holds the old modules, and its
   next lazy `from refmatrix.cli import …` meets the new layout. The announcement tells every
   session on the dev tree to `/mcp` reconnect after each phase's merge.
7. **Released alone.** One release holds this task and nothing else, so that a regression after
   it has one suspect. Who says go is `plan-review-fable D4`.
8. **No install window.** Nothing in this task may make `rmx install-hooks --check` report drift
   on an existing install (T0's R0.7, asked of all five plan-29 tasks). The hook generators
   import nothing from `cli`; R0 confirms it, and G7's run in the dev tree shows it.
9. **The window closes** when the phase is on `master` and every clone has been told to
   re-clone or rebase.

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
  - G4: one private helper not re-exported;
  - G5: one test made to fail with a different E line than at the parent;
  - G8: one moved function edited by hand (a renamed local variable);
  - G9: a file of 3,001 lines;
  - G10: a census whose bypass is planted in the old file name only (it must not count as seen).
  The scratch runs are logged. A gate that has only ever been run on an identical tree has not
  been shown to check anything ([[feedback_clean_corpus_hides_a_dead_gate]]). {#ac-1}
- **AC-2: every move commit passes G1-G5 and G7-G10**, and the summary has one row per commit:
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
- **AC-4: the entry points work as processes.** In a child process: `python -m refmatrix.cli
  version` exits 0 and reports this checkout; with `OBJC_DISABLE_INITIALIZE_FORK_SAFETY` unset
  it re-execs and still exits 0; after the re-exec no module in `sys.modules` was loaded as a
  top-level name from `src/refmatrix/cli/`; the `rmx` console script resolves
  `refmatrix.cli:cli_entry`. The naming census fails on a synthetic `cli/json.py`.
  `tests/test_fork_safety_reexec.py` is unchanged and green. {#ac-4}
- **AC-5: the derive tables name real files.** The new test fails, by name, when a table entry
  is missing on disk (must-fail: a tmp copy with one file removed). Every `store_*.py` is in
  `_DERIVE_CODE_MODULES`. A second test fails when a `store_*.py` file exists that the tuple
  does not name. {#ac-5}
- **AC-6: no private name crosses a module.** The census passes on the tree with an empty allow
  list, and fails on a synthetic module that imports `_x` from another `refmatrix` module, on
  one that reads `other._x` through an alias, and on one that does it inside a function (a
  lazy import). It passes on `cli/x_cmds.py` reading `_cli._root`. The summary's table has one
  outcome for each of the rows R0 listed. {#ac-6}
- **AC-7: no module produced by the split is over 3,000 lines.** The size census is green;
  `cli/*` and `store*.py` hold no exception; it fails on a 3,001-line file under `cli/` and on
  an excepted file that grew by one line. For `daemon.py`, `verbs.py` and `ingest.py`: the
  written assessment ([[#r7-assessed]]) is in the summary, and each is under the ceiling or
  has an exception row with an owner task that exists, as plan-29 D17's answer (or, with no
  answer, its pending default) decides. {#ac-7}
- **AC-8: the citation tool is ready and its dry run is recorded.** On fixture specs the tool
  rewrites a line cite to the right symbol when the def moved, resolves the line at the spec's
  own sha and not at `HEAD` (a fixture where the two differ), lists a module-level line as
  unresolved without guessing, and lists a qualified-name pin and a non-recursive glob as pins.
  The dry run over `workflow/plans/` is in the summary: per spec, resolved, unresolved, pins.
  No spec is rewritten by this task ([[#r8]] item 4). {#ac-8}
- **AC-9: the window was real.** The summary quotes the pre-phase checks of [[#r9]] item 1 with
  their output, the announcement, and the close. {#ac-9}
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
- **AC-13: the engine does not import the adapter.** The layering census passes with an empty
  allow list, and fails on a synthetic engine module that imports `refmatrix.cli` at module
  level and on one that does it inside a function. `handoff.py` and `telemetry.py` import
  nothing from `refmatrix.cli`. {#ac-13}
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
  14. `handoff.py` regains one lazy `from refmatrix.cli import` (AC-13);
  15. the symbol map drops the moved `Store` methods (AC-11's count test).
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
| `tools/dump_click_tree.py`, `tools/repoint_citations.py`, `tools/module_size_exceptions.json` | new |
| `handoff.py`, `telemetry.py`, and the modules R0 names as homes | phase 0b ([[#r2b]]) |
| `src/refmatrix/cli.py` → `src/refmatrix/cli/__init__.py`, `cli/__main__.py`, `cli/*_cmds.py` (14) | phase 1 |
| `src/refmatrix/store.py`, `src/refmatrix/store_*.py` (10) | phase 2 |
| the modules on R6's list (24 files at `f3709d2`) | phase 3 |
| `daemon.py`, `verbs.py`, `ingest.py` | assessed; changed only as plan-29 D17 and [[#r7]]'s criteria decide |
| `tests/test_split_module_tool.py`, `tests/test_click_tree_dump.py`, `tests/test_cli_patch_surface.py`, `tests/test_cli_entry_points.py`, `tests/test_derive_tables_name_real_files.py`, `tests/test_private_cross_module_census.py`, `tests/test_import_layering_census.py`, `tests/test_module_size_census.py`, `tests/test_symbol_map.py`, `tests/test_repoint_citations.py` | new |
| the test files in the source-reader inventory (about 20 at `f3709d2`; the queue review counts 31 that name the two files at all) | path literals, census keys, one recursive glob; nothing else |
| `tests/tiering.py` | `ALWAYS_FILES` gains this task's census tests ([[task-29.4-suite-health#r6]]) |
| `docs/architecture/module-split-map.md`, `docs/architecture/ARCHITECTURE_INDEX.md` | new map; index row |
| `docs/ARCHITECTURE.md`, `docs/SYSTEM.md`, `.claude/PROJECT_PROFILE.md`, `CLAUDE.md` | [[#r10]] |
| `workflow/bug_registry.md` | any row the task opens or closes |
| `workflow/implementation_summaries/task-29.5-split-giant-modules.md` | new: R0, the per-commit gate table, the symbol map, R6's table, the three assessments, the citation dry run, the window record |
{#files-table}

No spec under `workflow/plans/` is edited by this task: the citation pass is the plan's closing
step ([[#r8]]). {#files-no-specs}

## Out of scope {#out-of-scope}

- **Any behaviour change.** No bug is fixed in a move commit, including ones the move makes
  obvious. They are logged and scheduled in 29.1's grammar.
- **Splitting `daemon.py`, `verbs.py` or `ingest.py` outside what plan-29 D17 and [[#r7]]'s
  criteria allow.**
- **Decomposing `Store`** into collaborating objects ([[#r1]]).
- **Moving the core out of `cli/__init__.py`.** It stays where the patches expect it. Moving it
  means changing how tests reach it, which is a task about tests.
- **Re-pointing the 742 test → `src` private uses**, and typing anything: 29.2 and 29.3 land in
  the modules this task makes ([[plan-29-code-quality#order]]).
- **Rewriting any spec's citations** ([[#r8]] item 4), and revising any spec's pins.
- **Deleting dead code** ([[#r0]] item 9): its owners do that.
- **A formatter pass** over moved code. A reformat would make G8 meaningless.
- **Changing the fork-safety re-exec** ([[#fact-argv]]). Running it as `-m` would put the
  current directory first on the daemon's import path; today's form does not. That is a
  behaviour question for another task, and the naming census makes today's form safe.
- **Deciding** `plan-review-fable D4` or `plan-review-fable-store D5`.
{#out-of-scope-list}

## Open user decisions (referenced, not settled) {#open-decisions}

| Label | Question | Where this spec waits on it |
|---|---|---|
| `plan-review-fable D4` | A standing go for plan-29's releases when the suite equals baseline by E line, or a go per release | [[#r9]] item 7: this task's release, alone |
| `plan-review-fable-store D5` | Raise the dev venv from duckdb 1.5.2 to the 1.5.3 floor before baselines are taken | [[#r0]] item 12: no golden and no baseline before it is resolved |
| **plan-29 D17** (this spec's own) | What "no module over the size target" means for `daemon.py`, `verbs.py` and `ingest.py` | [[#r7]]: the pending default is built unless the user answers otherwise; phases 0 to 2 do not wait on it |
{#open-decisions-table}

`plan-review-fable D1` (do the three "right after 0.83.0" tasks come before plan-29) and
`plan-review-fable-memory D1` and `D2` (bug-241 and `legs_ms` ahead of the split) decide what is
already on `master` when the window opens. [[#r0]] item 10 records the answers; it does not
give them. {#open-decisions-upstream}

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
- **plan-29 D17 (open, for the user): what "no module over the size target" means for
  `daemon.py`, `verbs.py` and `ingest.py`.**
  - **The conflict:** the plan's 29.5 text splits `cli.py` and `store.py` and says `daemon.py`
    "is assessed after, not split by default"; its acceptance says "no `src/refmatrix` module
    over the size target". `daemon.py` is 7,355 lines, `verbs.py` 3,653, `ingest.py` 3,144.
  - **Pending default, in the spec until answered:** assess all three by [[#r7]]'s criteria;
    split in this task the ones that pass; the others get a dated exception with an owner task,
    and the size census holds them at their current size.
  - **The alternatives:**
    - (a) all three are split in 29.5, whatever the criteria say. For `daemon.py` that means
      also splitting the `Daemon` class and re-keying every census that names `_op_*`;
    - (b) 29.5 closes at `cli` + `store`; all three are assessed exceptions and none is split
      here. A later task takes whichever the assessments recommend. **This is the queue
      review's reading** (`#b1`: "no module produced by the split over target, with `daemon.py`,
      `verbs.py` and `ingest.py` listed as assessed exceptions"; it also defers "any `daemon.py`
      split").
  - **How far apart the default and (b) are:** `daemon.py` does not pass criterion 5 while 23.x
    and 18.x are approved and unbuilt, so under the default it is an exception too. The two
    differ only on `verbs.py` and `ingest.py`, and only if their assessments pass.
  - **Why not decided here:** the two sentences are both the user's approved text, and the
    choice moves days of an exclusive window. The lead puts it to the user (2026-11-14).
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
- **plan-29 D22: what the engine calls is moved down before the split (phase 0b), and the
  citation pass is handed to the end of the plan.**
  - **Why:** both avoid doing a thing twice: an engine function moved into a command module
    and then out of it; a spec re-pointed now and again after 29.3 renames helpers.
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
its pending default (the review's reading is recorded as alternative (b)); [[#r8]] publishes the map and the tool
here and hands the rewriting pass to the plan's end; [[#r9]] gains the MCP reconnect, the
release-alone rule and the no-drift rule; the baseline is 29.4's stage 5. {#rev-note-body}

