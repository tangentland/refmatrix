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
> Depends on: [[task-29.4-suite-health]] (its runner's `--compare` is the equality gate this
> task runs around every commit, and its 20-minute suite is what makes that affordable);
> [[task-29.1-registry-triage]] (rows this task touches are closed in its grammar).
> Runs third in plan-29's order: 29.1 → 29.4 → **29.5** → 29.2 ∥ 29.3.
> **Runs alone:** in an announced window with no other `src/` work in flight ([[#r9]]).
> User gates: the window's start (the lead announces it; the user may hold it), and one open
> decision, plan-29 D17 ([[#decisions]]).
> Before the first move: an ADR for the module layout, authored by `ch-architect` ([[#r1]]).

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
| `python -m refmatrix.cli` spawn sites | 7 in `src/` (6 files, among them `daemon.py:7059`, `scheduler.py:131`, `ui/server.py:191` and `:578`); 22 in tests (8 files) |
| `src` modules that import from `cli` | 2: `handoff.py` (three private names, lazily, "cli->handoff cycle") and `telemetry.py` (`main`) |
| `global` statements in `cli.py` | 5: `_partition_override` × 4, `file` × 1 |
{#baseline-reach-table}

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
seven frozen spec branches are not in this count; R0 counts again after they merge.
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
and the size gate in [[#r7]] is what binds.

### `refmatrix/cli/` {#map-cli}

Command callbacks go to the module of their top-level click name. A helper goes with its only
user; a helper used by two or more command modules, or by none inside `cli.py`, stays in the
package's `__init__.py`. Lines are what the tool would write at `f3709d2` (sum 15,212).

| Module | Lines | Callback lines | Helpers | Top-level click names |
|---|---|---|---|---|
| `cli/__init__.py` (the core) | 1,622 | 0 | 48 (1,367 lines) | the `main` group, `cli_entry`, `_reexec_for_fork_safety`, `_root`, `_store`, `_DaemonWriter`, `console`, module state; imports the command modules last |
| `cli/__main__.py` | new, ~5 | | | `from refmatrix.cli import cli_entry` then `cli_entry()` |
| `cli/memory_cmds.py` | 2,238 | 1,149 | 22 | `memory`, `taxonomy` |
| `cli/session_cmds.py` | 2,223 | 1,791 | 24 | `focus`, `session`, `task`, `save-state`, `recall-state`, `scan-prompt`, `cctree` |
| `cli/search_cmds.py` | 2,036 | 676 | 24 | `context`, `grep`, `recall`, `search-dense`, `locate` |
| `cli/store_cmds.py` | 1,842 | 1,735 | 8 | `partition`, `replica`, `derive`, `canon`, `repair-index`, `compact`, `compact-log`, `rebuild`, `vacuum`, `checkpoint`, `dump-log`, `migrate-to-duckdb`, `merge-verb-aliases`, `audit-same-as`, `prune-noise`, `forget`, `protect`, `unprotect`, `noise`, `unnoise`, `link`, `unlink`, `add` (and its 3 hidden aliases) |
| `cli/ingest_cmds.py` | 1,745 | 1,309 | 13 | `ingest`, `ingest-gmd`, `ingest-status`, `sync`, `reingest`, `embed`, `tldr-warm`, `graphify-warm`, `init`, `untrack`, `import`, `export`, `coref`, `pairs` |
| `cli/daemon_cmds.py` | 1,466 | 1,299 | 6 | `daemon`, `queue`, `learn`, `watch`, `log`, `cli-log`, `telemetry`, `fingerprint` |
| `cli/hub_cmds.py` | 1,019 | 911 | 9 | `hub`, `bus`, `schedule`, `ui`, `projects`, `mcp`, `curator`, `refine` |
| `cli/query_cmds.py` | 877 | 742 | 4 | `query`, `describe`, `neighbors`, `top`, `co-occur`, `concept`, `stats`, `info`, `list` (and its 3 hidden aliases), `run`, `save-query`, `primer`, `tools-primer`, `pagerank` |
| `cli/admin_cmds.py` | 144 | 144 | 0 | `install-hooks`, `upgrade`, `version` |
{#map-cli-table}

The largest module is 2,238 lines. A first cut with `context` and `grep` in `query_cmds` came
to 2,946, too close to the ceiling, so search has its own module. {#map-cli-note}

### `store.py` and its concern modules {#map-store}

`Store` stays one class with one name and one import path. Its methods move, by the section
banners already in the file, into mixin classes in sibling modules; `store.py` keeps the
module-level code, the class statement, construction and lifecycle. Lines by banner at
`f3709d2` (sum 9,246):

| Module | Lines | Holds (banner sections of `Store`) |
|---|---|---|
| `store.py` | 2,559 | everything before the class (1,278: constants, the derive tables, helper functions, `Entity`, the error classes); the class header and `__init__` (227); **lifecycle** (1,054: connect, slots, snapshot, locks) |
| `store_fragments.py` | 1,741 | linkage types (158), **bitmaps / fragments** (1,494), canon (89) |
| `store_removal.py` | 1,426 | purge / track files (1,121), vacuum (163), noise pruning (112), sync log (30) |
| `store_memory.py` | 1,099 | intuition **memory** layer (314), subjects (785) |
| `store_entities.py` | 1,082 | entities / concepts (225), pending `rel:` references (89), `denotes` (468), coref sidecar + pair index (238), saved queries (29), stats (33) |
| `store_log.py` | 740 | log dump / rebuild |
| `store_vectors.py` | 599 | dense **vector** wrappers |
{#map-store-table}

A banner is where a method sits, not proof of what it is about (`content_rank`, 366 lines, is
the largest method; R0 says which section holds it and whether it belongs there). R0 re-cuts by
reading, and the tool takes the result as its map. {#map-store-note}

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
   summary and in the deploy note. No guess: read the callers.

### R1: the decision is recorded first {#r1}

The layout below is an architectural decision: a size ceiling, a package whose core is
late-bound, a class composed from concern mixins, and what "private" means across modules.
`ch-architect` authors it as the next ADR in `docs/adr/` (0006 at `f3709d2`), through
`/ch-crucible`, before the first move commit, with a row in `docs/adr/0000-adr-overview.md` and
`docs/INDEX.md`. [[#r2]], [[#r5]], [[#r6]] and [[#r7]] are its inputs. If review of the ADR
changes a rule, this spec is revised before any code moves. {#r1-body}

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
   when one command module is its only user (five helpers at `f3709d2`, among them
   `_grep_stdin_addendum`).
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

### R3: every move is made by a tool {#r3}

`tools/split_module.py` reads a map file (`tools/split_maps/cli.json`, `store.json`: def name →
target module) and writes the result. "Mechanical" in this task means exactly: **the tool
produced it.**

- For each moved top-level def: its source lines, with the comments and blank lines directly
  above it, are moved verbatim; then the substitutions of [[#r2]] items 2 and 3 are applied
  from the syntax tree, and nothing else.
- For `Store` methods: the method's lines move verbatim into a mixin class body
  (`class _StoreFragments:`), and module-level names of `store.py` that the method uses become
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

**Order.** Phase 0 builds the gates. Phase 1 is `cli`. Phase 2 is `store`. Phase 3 is the
private names. Each commit lands on the task branch; the branch merges to `master` once, at
the end of a phase.

| Phase | Commits |
|---|---|
| 0 | the tool and its tests; the gates and goldens of this section, generated at the base sha and committed; the inventories of [[#r0]] |
| 1 | `git mv cli.py cli/__init__.py` with `cli/__main__.py` (a rename and one new file; the source-reader tests that name the path are re-pointed here); then one commit per command module, smallest first: `admin_cmds`, `query_cmds`, `hub_cmds`, `daemon_cmds`, `ingest_cmds`, `store_cmds`, `search_cmds`, `session_cmds`, `memory_cmds` |
| 2 | one commit per concern module: `store_vectors`, `store_log`, `store_entities`, `store_memory`, `store_removal`, `store_fragments`; each extends `_DERIVE_CODE_MODULES` with its file ([[#r5]]) |
| 3 | [[#r6]], one commit per target module |
{#r4-phases}

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
- `master` is tagged `pre-split-29.5` before phase 1 merges.

### R5: `store.py` by concern {#r5}

1. `class Store(_StoreVectors, _StoreLog, _StoreEntities, _StoreMemory, _StoreRemoval,
   _StoreFragments):` in `store.py`. The mixins hold methods only: no `__init__`, no class
   attributes that `Store` also defines, no state of their own. A census test checks all
   three, and checks that no method name is defined in two mixins.
2. `from refmatrix.store import Store` and every other name importable from `refmatrix.store`
   today still resolves there (G4). `Store.<method>` patches still work: a class attribute set
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
  At `f3709d2` it has 55 rows (76 sites). Each row ends as one of:
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
entries in `tools/module_size_exceptions.json` (file, lines when listed, reason, owner task).
An excepted file may not grow past its listed size. A new file gets no exception.

- After phase 2, `cli/*` and `store*.py` hold no exception.
- **`daemon.py` (7,355), `verbs.py` (3,653), `ingest.py` (3,144)** are over the ceiling and are
  not `cli` or `store`. The plan says `daemon.py` "is assessed after, not split by default",
  and its acceptance says "no module over the size target". This spec reads the two together
  as: each of the three gets a written assessment in the summary, by fixed criteria, and then
  either a split in this task by the same tool and gates, or an exception with a named owner
  task. **This reading is plan-29 D17 and needs the user** ([[#decisions]]).
- **The criteria** (all must hold to split here):
  1. a seam exists that the tool can cut: registered functions (`daemon.py`'s 89 `_op_*`
     functions, 2,339 lines; `verbs.py`'s verb registry) or banner sections of one class;
  2. the patch inventory for the module leaves every patched name in the origin module
     (tests patch `daemon` attributes at 248 sites, 23 names; `verbs` at 61, 18);
  3. no move commit needs a test edit outside the source-reader rule;
  4. the result is under the ceiling. For `daemon.py` that takes both the ops (2,339) and the
     `Daemon` class (2,668 lines, 70 methods), since removing the ops alone leaves 5,016.
- `ingest.py` at 3,144 is 5% over. If it is not split, its exception is the smallest case and
  says so.

### R8: specs that cite a line get a symbol {#r8}

- `tools/repoint_citations.py` rewrites `cli.py:NNNN` and `store.py:NNNN` in every spec under
  `workflow/plans/` whose `metadata.status` is not completed (44 files, 271 sites at
  `f3709d2`). For each site it takes the spec's last-change sha, finds the def that held line
  NNNN in the module **at that sha**, and writes the def's new home as
  `` `cli/<module>.py::<def>` `` or `` `store_<concern>.py::Store.<method>` ``. A symbol does
  not rot when lines move; T0's R0.1 already found `store.py:717` at `:1159`.
- A site whose line was module-level code, or whose def no longer exists, is not guessed. It is
  listed in the summary with the spec and the old text, and the spec's owner re-reads it.
- **History is not rewritten.** Completed specs, handoffs, summaries and the ledger keep their
  citations (759 + 394 sites). `docs/architecture/module-split-map.md` (GMD, generated by the
  tool from the two map files) lists every moved def with its old file and its new one, and
  `docs/architecture/ARCHITECTURE_INDEX.md` links it, so an old citation can be resolved.
- The frozen spec branches merge before plan-29, so their specs are in the set. A spec written
  while this task runs cites symbols from the start; the lead says so when it announces the
  window.

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
4. **The merge to the dev tree is announced as a store event.** It deletes `cli.py` from a
   watched tree and adds eleven files; the live store's daemon purges the old path's entities and
   re-ingests. bug-177 (hook timeouts during a large post-merge sync) and bug-107 (learned rows
   deleted with a purged path) both apply. The lead counts the learned rows on `cli.py` and
   `store.py` before the merge and backs up first; this task's agents do not touch the store.
5. **Deploy** is the lead's, from a committed `master` sha, after a phase's merge. The deploy
   note carries: R0 item 8's answer; that `~/refmatrix/src/refmatrix/cli.py` must be absent
   after the fast-forward; the smoke checks (`rmx version -v`, `python -m refmatrix.cli version`
   in the deploy venv, a daemon restart and status, an MCP reconnect).
6. **The window closes** when the phase is on `master` and every clone has been told to
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
  - G9: a file of 3,001 lines.
  The scratch runs are logged. A gate that has only ever been run on an identical tree has not
  been shown to check anything ([[feedback_clean_corpus_hides_a_dead_gate]]). {#ac-1}
- **AC-2: every move commit passes G1-G5 and G7-G9**, and the summary has one row per commit:
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
- **AC-7: the size census is green**, with `cli/*` and `store*.py` under 3,000 lines and no
  exception for them. For `daemon.py`, `verbs.py` and `ingest.py`: the assessment is in the
  summary; each is under the ceiling or has an exception row with an owner task that exists
  (per plan-29 D17's answer). {#ac-7}
- **AC-8: citations.** No not-completed spec under `workflow/plans/` matches
  `\b(cli|store)\.py:\d+`, except the sites the tool listed as unresolved, each of which is in
  the summary. `module-split-map.md` exists, lints clean, and holds one row per moved def (the
  tool's own count). {#ac-8}
- **AC-9: the window was real.** The summary quotes the pre-phase checks of [[#r9]] item 1 with
  their output, the announcement, and the close. {#ac-9}
- **AC-10: before and after.** The [[#baseline]] tables, re-measured at the final sha, are in
  the summary beside R0's. `./scripts/lint-gmd.sh` exits 0. {#ac-10}

## Test strategy {#test-strategy}

- **A move has no RED, so the gates are what is test-driven.** Phase 0 is ordinary TDD: the
  tool's tests, the dump tool's tests, the census tests and AC-3's probes are written first and
  recorded failing (the tool does not exist; the censuses' must-fail cases are RED), then made
  green. Phase 0 changes no production behaviour.
- **Characterisation tests are proven by mutation, not by a RED run.** AC-3's probes and AC-4's
  process tests pass before the split and must pass after it; a RED run at base is impossible
  by design. Each is shown able to fail by its mutation below.
- **Phase 3 is ordinary TDD** (the census's must-fail case is RED; each rename follows).
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
      script must refuse two runs with one sha).
- **The suite runs before and after every phase-1 and phase-2 commit** (G5). At 29.4's target
  that is about 16 move commits × 2 runs × 20 minutes, with each commit's "after" serving as
  the next commit's "before": about 17 runs, under 6 hours of machine time, not of anyone's
  attention.
- **All output to files**, through 29.4's runner, under `workflow/review-output/task-29.5/`.
{#test-strategy-list}

## Files {#files}

| File | Change |
|---|---|
| `docs/adr/0006-*.md`, `docs/adr/0000-adr-overview.md`, `docs/INDEX.md` | the layout decision ([[#r1]]; authored by `ch-architect`) |
| `tools/split_module.py`, `tools/split_maps/cli.json`, `tools/split_maps/store.json` | new: the move tool and its maps |
| `tools/dump_click_tree.py`, `tools/repoint_citations.py`, `tools/module_size_exceptions.json` | new |
| `src/refmatrix/cli.py` → `src/refmatrix/cli/__init__.py`, `cli/__main__.py`, `cli/*_cmds.py` (9) | phase 1 |
| `src/refmatrix/store.py`, `src/refmatrix/store_*.py` (6) | phase 2 |
| the modules on R6's list (24 files at `f3709d2`) | phase 3 |
| `daemon.py`, `verbs.py`, `ingest.py` | only as plan-29 D17 and [[#r7]]'s criteria decide |
| `tests/test_split_module_tool.py`, `tests/test_click_tree_dump.py`, `tests/test_cli_patch_surface.py`, `tests/test_cli_entry_points.py`, `tests/test_derive_tables_name_real_files.py`, `tests/test_private_cross_module_census.py`, `tests/test_module_size_census.py` | new |
| the test files in the source-reader inventory (about 20 at `f3709d2`) | path literals, census keys, one recursive glob; nothing else |
| `tests/tiering.py` | `ALWAYS_FILES` gains this task's census tests ([[task-29.4-suite-health#r6]]) |
| the not-completed specs under `workflow/plans/` (44 at `f3709d2`); `docs/` | [[#r8]], [[#r10]] |
| `docs/architecture/module-split-map.md`, `docs/architecture/ARCHITECTURE_INDEX.md` | new map; index row |
| `.claude/PROJECT_PROFILE.md`, `CLAUDE.md` | [[#r10]] |
| `workflow/bug_registry.md` | any row the task opens or closes |
| `workflow/implementation_summaries/task-29.5-split-giant-modules.md` | new: R0, the per-commit gate table, R6's table, the assessments, the window record |
{#files-table}

## Out of scope {#out-of-scope}

- **Any behaviour change.** No bug is fixed in a move commit, including ones the move makes
  obvious. They are logged and scheduled in 29.1's grammar.
- **Moving the core out of `cli/__init__.py`.** It stays where the 191 patches expect it. Moving
  it means changing how tests reach it, which is a task about tests.
- **Re-pointing the 742 test → `src` private uses**, and typing anything: 29.2 and 29.3 land in
  the modules this task makes ([[plan-29-code-quality#order]]).
- **Splitting `mcp.py`** (389 lines) or any module under the ceiling.
- **A formatter pass** over moved code. A reformat would make G8 meaningless.
- **Changing the fork-safety re-exec** ([[#fact-argv]]). Running it as `-m` would put the
  current directory first on the daemon's import path; today's form does not. That is a
  behaviour question for another task, and the naming census makes today's form safe.
{#out-of-scope-list}

## Decisions taken in this spec {#decisions}

- **plan-29 D16: the core stays in `cli/__init__.py`, and moved code reads it as
  `_cli.<name>`.**
  - **Why:** 191 test patches (160 of them on `_root`) and the conftest's per-test reset of
    `_partition_override` act on the module `refmatrix.cli`. With the core there and late-bound
    reads, every one of them means what it meant, with no test edited. The other shapes (a
    `_core.py` that tests are re-pointed to; names imported into each command module) either
    change 191 test sites in the same commit as the code they check, or make the patches
    silently miss.
  - **Cost:** `_cli.` in front of core names in moved code, and a 1,622-line `__init__.py`.
- **plan-29 D17 (open, for the user): what "no module over the size target" means for
  `daemon.py`, `verbs.py` and `ingest.py`.**
  - **The conflict:** the plan's 29.5 text splits `cli.py` and `store.py` and says `daemon.py`
    "is assessed after, not split by default"; its acceptance says "no `src/refmatrix` module
    over the size target". `daemon.py` is 7,355 lines, `verbs.py` 3,653, `ingest.py` 3,144.
  - **Taken here, pending the answer:** assess all three by [[#r7]]'s criteria; split in this
    task the ones that pass; the others get a dated exception with an owner task, and the size
    census holds them at their current size.
  - **The alternatives:** (a) all three are split in 29.5, whatever the criteria say, which
    for `daemon.py` means also splitting the `Daemon` class and re-keying every census that
    names `_op_*`; (b) 29.5 closes at `cli` + `store` and a task 29.6 takes the rest.
  - **Why not decided:** the two sentences are both the user's approved text, and the choice
    moves several days of an exclusive window.
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
    mangling and no `super()` to break). Composition by delegation would be a rewrite, not a
    move.
  - **Cost:** `Store`'s method resolution order is now part of the design; R5's census keeps the
    mixins from overlapping.
- **Not decided here, because the plan decided it:** `cli` becomes a package, one module per
  command group; moves only; one group per commit; the ceiling is about 3,000 lines.
{#decisions-list}
