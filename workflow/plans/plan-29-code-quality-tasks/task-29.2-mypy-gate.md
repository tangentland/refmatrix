---
gmd: "0.1"
id: task-29.2-mypy-gate
title: "Task 29.2: a mypy commit gate — strict on verbs / query / store / handoff / mcp, a baseline that only falls for the rest, and the casts that hide a real type removed (bug-235)"
tags: [task, plan-29, typing, mypy, gate, protocol, query, pql, code-quality]
metadata:
  node_type: task
  status: pending
  plan: plan-29-code-quality
  created: 2026-11-14
  updated: 2026-11-14
---

# Task 29.2: the mypy gate {#root}

> Plan: [[plan-29-code-quality]] ([[plan-29-code-quality#t2]])
> Status: Pending
> Depends on: 29.4 (the healed suite) and 29.5 (the module split), per
> [[plan-29-code-quality#order]]. Runs AFTER the query half of [[task-29.3-converge-shapes]];
> the files both touch are ordered in [[#seam]].
> Review input folded 2026-11-14: `plan-review-fable-2026-11-14-queue#b1`,
> `plan-review-fable-2026-11-14-queue#p29-4`,
> `plan-review-fable-2026-11-14-store#plan29-converge-candidates` ([[#fold]]).
> Open for the user: `plan-29 D4` ([[#d4]]).

rel: part-of -> [[plan-29-code-quality]]
rel: implements -> [[tdd-governance]]
rel: depends-on -> [[bug_registry#registry]]
rel: related-to -> [[task-29.3-converge-shapes]]
rel: reinforces -> [[feedback_clean_corpus_hides_a_dead_gate]]
rel: reinforces -> [[feedback_converge_repeated_shapes]]
rel: derives-from -> [[bsd-pattern-prereg-check-unrun-census]]
rel: derives-from -> [[bsd-pattern-guard-cannot-fire]]
rel: realizes -> [[constitution#project-1]]

## What this task delivers {#summary}

1. `scripts/check-types.sh`: one command that runs mypy over `src/refmatrix` and exits 0 only when
   the strict modules have zero errors and no other module has more errors than its recorded
   baseline.
2. A baseline file whose counts can only go down.
3. `QueryEngine.run_pql` returns a typed result, which closes bug-235.
4. `_DaemonWriter` and `Store` meet one `typing.Protocol`; `_DaemonWriter.__getattr__` is removed.
5. No `typing.cast` is left in `src/refmatrix`.

## Measured at `f3709d2` (before the 29.5 split) {#measured}

Every number below came from a script or a log that is committed with this spec
([[bsd-pattern-prereg-check-unrun-census#rule]]: a census sentence names its script and commit).
Scripts: `workflow/plans/plan-29-code-quality-tasks/census/`. Logs: `workflow/review-output/`.
mypy 2.4.1, Python 3.14, 78 source files. The task re-runs all of them at its own start commit
([[plan-29-code-quality#baseline-rule]]) and records the new numbers in its summary. {#measured-rule}

**Environment caveat.** `.venv-eval` has duckdb 1.5.2; `pyproject.toml` requires `>=1.5.3`
(`plan-review-fable-store D5`, an open user decision that this spec does not settle). duckdb
ships its own type stubs, and mypy reads them from the installed version, so the counts in
modules that use duckdb types can differ under 1.5.3. That was not measured: nothing was
installed for this spec. Whatever D5 decides, [[#r3]] makes the baseline name the duckdb version
it was recorded with. {#measured-duckdb}

### mypy with no configuration {#measured-default}

`mypy src/refmatrix` (log `mypy-baseline.log`, summary by `census/mypy_summary.py`):
**203 errors in 30 of 78 files**, 12.4 s wall.

| module | errors | module | errors | module | errors |
|---|---|---|---|---|---|
| store | 31 | ingest_gmd | 7 | recall_pack | 2 |
| context | 25 | hub | 7 | memory_layout | 2 |
| daemon | 19 | hooks | 6 | embed_worker | 2 |
| cli | 14 | modelsrv | 5 | sync | 1 |
| recall | 11 | consolidate | 5 | subproc | 1 |
| telemetry | 10 | cctree | 4 | search | 1 |
| stm | 10 | memory_index | 3 | pagerank | 1 |
| ingest | 10 | handoff | 3 | models_local | 1 |
| verbs | 8 | scan | 2 | launchctl | 1 |
| ui/server | 8 | reranker | 2 | helix | 1 |

Top error codes: `assignment` 57, `attr-defined` 38, `arg-type` 38, `union-attr` 15,
`var-annotated` 13, `dict-item` 8, `index` 7, `operator` 6, `misc` 6, `name-defined` 5,
`return-value` 4. `query` and `mcp` have 0 errors here, because an unannotated function body is
not checked by default. {#measured-default-codes}

The same run with `--python-version 3.10` (the floor `pyproject.toml` declares) gives the same
203 errors on the same lines (`mypy-py310-probe.log`). {#measured-py310}

### mypy under the configuration this task wires {#measured-gate}

Config `census/mypy-gate-probe.ini`: `check_untyped_defs`, `warn_unused_ignores` and
`warn_redundant_casts` everywhere; the strict flags of [[#r2]] on the five modules. Log
`mypy-gate-probe.log`: **716 errors = 527 in the five strict modules + 189 in 29 other modules.**

| strict module | errors | by code |
|---|---|---|
| store | 257 | type-arg 133, no-untyped-call 49, no-untyped-def 31, assignment 22, no-any-return 11, arg-type 4, index 3, misc 2, name-defined 1, attr-defined 1 |
| verbs | 212 | type-arg 137, no-untyped-call 29, no-untyped-def 25, no-any-return 13, arg-type 5, other 3 |
| handoff | 27 | type-arg 15, no-untyped-def 5, no-untyped-call 4, assignment 2, str-unpack 1 |
| mcp | 22 | type-arg 10, no-untyped-call 7, no-untyped-def 5 |
| query | 9 | type-arg 3, no-untyped-def 3, no-untyped-call 2, var-annotated 1 |

The 527 are the work of [[#r2]]: 298 are `type-arg` (a bare `dict` / `list` in a signature), 91
`no-untyped-call`, 69 `no-untyped-def`, 24 `no-any-return`. The other 189 are the starting
baseline of [[#r3]]: cli 32, context 25, daemon 22, telemetry 12, stm 11, recall 11, ingest 10,
ui/server 8, ingest_gmd 7, hub 7, hooks 6, and 18 modules with 5 or fewer. {#measured-gate-split}

Public surface of the five (`census/census_public_annotations.py`, log
`census-public-annotations-f3709d2.log`): 233 public functions and methods, 208 fully annotated,
25 not (store 15, verbs 5, handoff 3, query 1, mcp 1). {#measured-public}

Two more probes, kept for the record:

- `mypy --strict` on everything: 2,422 errors in 67 files (`mypy-strict-probe.log`). This is NOT
  the target; it shows what "strict everywhere" would cost.
- A per-module section that says `strict = True` gives exactly that global result (2,422, the
  same per-module counts; `mypy-per-module-strict-key-probe.log`). In mypy 2.4.1 the `strict` key
  is not per-module, so the strict modules must list the individual flags. {#measured-strict-key}
- A section pattern with a partial wildcard (`refmatrix.sto*`) is rejected with one line
  ("Patterns must be fully-qualified module names, optionally with '*' in some components") and
  mypy then RUNS with that section ignored: 203 errors, none of them from the section's flag
  (`mypy-wildcard-pattern-probe.log`). So `refmatrix.store_*` cannot name 29.5's mixin modules,
  and a mistyped pattern leaves a module un-strict without failing the run. {#measured-wildcard}

### Casts and other ways a type is hidden {#measured-casts}

`grep -rn "cast(" src/refmatrix` finds 4 lines; 3 are `typing.cast`.

| site (symbol; file at `f3709d2`) | what it does | class | action |
|---|---|---|---|
| `_store` (`cli.py`): `cast(Store, _DaemonWriter(...))` | says a proxy with 18 methods and a `__getattr__` is a `Store` | HIDES a real type | removed by [[#r5]] |
| `QueryEngine.run_pql` (`query.py`): `cast("BitMap \| list", ...)` | hides the `int` that `Count()` returns; its own NOTE admits it | HIDES a real type (bug-235) | removed by [[#r4]] |
| `Store._connect` (`store.py`): `cast(sqlite3.Connection, con)` | narrows the backend connection after `self._backend.kind == "sqlite"` | true at run time, unchecked | replaced by an `isinstance` narrowing, [[#r6]] |
| `vectors.py`: `now_naive.cast(pa.timestamp(...))` | a pyarrow array method | not a typing cast | none; the census of [[#r6]] must not flag it |

`# type: ignore` comments: 5, all with an error code (`mcp` 2 `attr-defined`, `daemon` 2
`assignment`, `daemon` 1 `misc`). Under `warn_unused_ignores` mypy reports the two `assignment`
ones as the wrong code (`method-assign`). They are counted and ratcheted by [[#r6]]. {#measured-ignores}

### `_DaemonWriter` against `Store` {#measured-writer}

`census/census_writer_surface.py` (log `census-writer-surface-f3709d2.log`; every fall-through
site in `census-writer-surface-fallthrough-f3709d2.log`):

- `_DaemonWriter` defines 18 public methods and a `__getattr__`; `Store` defines 127.
- 1 proxy method has no `Store` method of that name: `ingest_path`.
- 5 of the 17 shared names have different parameter lists: `with_partition` (`partition` vs
  `name`), `forget_memory` (`target` vs `name_or_id`), `bulk_forget_memories` and `prune_noise`
  (positional vs keyword-only), `link_cross_doc_coref` (the proxy lacks `max_sentences`).
- 46 `_store(...)` writer calls. On the objects they return the scan sees 57 attribute uses:
  22 go to an explicit proxy method, and **35 uses of 20 attributes fall through `__getattr__` to
  the lock-free reader.** Of those 20, 11 are mutations (`rename_partition`, `merge_partition`,
  `link_many`, `link_part_of`, `upsert_subject`, `retag_memory`, `repair_fragments`,
  `repair_entity_links_index`, `rebuild_entities_indexes`, `dump_catalog_to_log`, and the private
  `_connect`, 6 uses, which `__getattr__` refuses with `AttributeError`).

Read from the code, not reproduced: the sites checked (`partition_add`, `partition_rename`,
`import_`, `_subject_upsert`, `_subject_link`, the `retag` fallback) all sit in a branch taken
when no daemon answered. They are safe only while that stays true between the gate and the call;
the cast is what lets them compile. The scan follows names inside one function only, so 35 is a
floor; mypy over the Protocol is the complete count. {#measured-writer-note}

## Requirements {#requirements}

### R1: one gate command {#r1}

- `scripts/check-types.sh` is the entry, written like `scripts/lint-gmd.sh`: it finds the repo
  root, requires `.venv-eval/bin/python`, and hands over to `scripts/check_types.py`, which holds
  the logic so tests can call it with other paths.
- It is a separate script. It does NOT join `lint-gmd.sh`: that gate is the docs gate, tests run
  it on docs fixtures, and bug-230 showed that a second step inside one gate can die unseen.
- `CLAUDE.md` gains the command in `#development-commands` and one checklist line in
  `#before-commit` ("type gate exit 0: `./scripts/check-types.sh`").
- A suite test runs the gate on the checkout and requires exit 0, so the full suite fails on a
  type regression. There is no CI and no git pre-commit hook for either gate today.
- `pyproject.toml`: `mypy>=2.4` joins the `dev` extra; the configuration lives in `[tool.mypy]`.
  Nothing is added to the runtime dependencies or to the deploy venv.
- Parameters, all with repo defaults: `--src`, `--config`, `--baseline`, `--cache-dir`,
  `--update`, `--rebaseline`. Tests pass a temp `--cache-dir`; the default `.mypy_cache/` is
  already git-ignored.

Exit codes are fixed, and each prints one summary line on stderr:

| exit | meaning |
|---|---|
| 0 | checked; every module at or under its baseline; no strict or new module has an error |
| 1 | type errors: an error in a module with no baseline cell, or a cell above its baseline |
| 2 | the gate could not run (see [[#r1-cannot-run]]) |
| 3 | the baseline is stale: a cell measured below its recorded count; run `--update` and commit |

**Cannot run is never clean.** Exit 2, with the remedy named, when: the dev interpreter is
missing; `import mypy` fails (`pip install -e '.[dev]'`); mypy exits with its own crash or usage
code; mypy prints a configuration diagnostic (any output line that is not an error, a note or
the summary; [[#measured-wildcard]] is one); the number of parsed error lines differs from mypy's
own `Found N errors` figure; mypy checked fewer files than there are `*.py` files under `--src`
(counted with `rglob`, so packages are included); or the installed mypy `major.minor` or duckdb
version differs from the one the baseline records. {#r1-cannot-run}

### R2: strict on the five public surfaces {#r2}

- **Strict set.** At `f3709d2`: `refmatrix.verbs`, `refmatrix.query`, `refmatrix.store`,
  `refmatrix.handoff`, `refmatrix.mcp`. After 29.5: those, plus every module that 29.5 split out
  of any of them (see [[#split]]). 29.5 turns `Store` into mixin classes in sibling modules
  `refmatrix.store_<concern>`; each one is listed BY NAME, because a `refmatrix.store_*` pattern
  is not valid ([[#measured-wildcard]]). AC-5 proves the list is complete.
- **Each mixin module type-checks on its own.** A mixin method that uses state or a method
  another mixin defines (`self._connect()`, `self._partition_id`) gets that from ONE declared
  host that every mixin shares (a common base class, or a Protocol used as the type of `self`).
  It is not typed by `Any`, by a `# type: ignore`, or by an attribute declared again in each
  mixin. Declaring the host changes no behaviour and adds no method.
- **Strict means the whole module**, private helpers included. mypy has no public / private
  switch, and an unannotated private helper returns `Any` into the public function that wraps it
  ([[#k1]]).
- **Flags**, listed one by one because of [[#measured-strict-key]]: `disallow_untyped_defs`,
  `disallow_incomplete_defs`, `disallow_untyped_calls`, `disallow_untyped_decorators`,
  `disallow_any_generics`, `disallow_subclassing_any`, `warn_return_any`, `no_implicit_reexport`,
  `strict_equality`, `extra_checks`.
- **Global flags** for every module: `python_version = "3.10"` ([[#measured-py310]]),
  `check_untyped_defs`, `warn_unused_ignores`, `warn_redundant_casts`, `warn_unused_configs`,
  `enable_error_code = ["ignore-without-code"]`.
- **Result:** zero errors in every strict module, with no `ignore_errors`, no per-module
  `disable_error_code`, and no new `# type: ignore` in them.
- An error that names an untyped function in a NON-strict module is fixed by annotating that
  function there. That lowers the other module's baseline; it is not a reason to relax a flag.

### R3: everything else on a baseline that only falls {#r3}

- `scripts/type-baseline.json` records the mypy `major.minor`, the duckdb version
  ([[#measured-duckdb]]), the commit it was recorded at, and one cell per (module, error code)
  with its count. Strict modules have no cells.
- **A module with no cell must be clean.** That one rule covers the strict set and every module
  created later: new modules are born clean.
- A cell above its count is exit 1. The message names the cell, both counts, and every mypy line
  in that cell.
- A cell below its count is exit 3. `--update` rewrites the falling cells and removes cells that
  reached zero. `--update` refuses (exit 1, file byte-identical) when any cell rose or a
  cell-less module has an error.
- A module rename moves its cells by hand in the same commit as the rename; `--update` never
  creates a cell.
- `--rebaseline` is the only path that can raise a count, and it exists for one case: a
  version change of mypy or of duckdb's bundled stubs. It records the new versions, never
  creates a cell for a strict module, and lands in a commit of its own whose message names the
  old and new versions.
- The task's summary records the total at the start commit and at the end. The end total is not
  above the start total.

### R4: `run_pql` returns what it computes (bug-235) {#r4}

- `refmatrix.query` defines the result as a tagged union of three small frozen types: a bitmap
  of entity ids, a weighted list of `(entity id, weight)`, and a count. `run_pql` is annotated
  with that union and holds no `cast`.
- `_PQLEvaluator.eval`, `_parse` and `_call` are annotated. The evaluator's internal value type
  also admits the bare names, strings and integers that are arguments; that value type is the
  one [[task-29.3-converge-shapes#b-r4]] defines, since 29.3's query half lands first
  ([[#seam]]). A value of one of those kinds at the TOP level is not a result: `run_pql` raises
  `ValueError("PQL: …")` naming it. 29.3(b) makes it so; AC-7 here holds it, and if this task
  runs first after all, it makes it so itself, because the union cannot be built without it.
- Every caller handles all three variants, and mypy proves it: each dispatch ends in an
  exhaustiveness check (an `assert_never`-style helper; `typing.assert_never` needs Python 3.11
  and the package floor is 3.10, so the helper is local, not a new dependency). Callers at
  `f3709d2`: the daemon op `_op_query`, the CLI `query` command (twice: the replica route and the
  direct route), and the `rmx_matrix` verb's `run` action.
- The `rmx_matrix` verb returns a count as `{"shape": "int", "value": n}`. That is the wire shape
  `_op_query` already returns and the CLI already renders. `rmx matrix run` prints the number.
  The registry row's proposed `{"count": n, "shape": "count"}` is not used ([[#k3]]).
- Every other payload stays byte-identical (`weighted`, `ids`, `bitmap` rows and keys).

### R5: one Protocol for the catalog writer {#r5}

- The store module family (strict) defines `StoreWriter`, a `typing.Protocol` naming every
  method a command body may call on what `_store(write=True)` returns. It lives in a leaf module
  that imports no mixin and nothing from the CLI package, so the mixin modules, `store.py` and
  `refmatrix/cli/` can all import it without a cycle.
- **It works with a mixin-composed `Store`.** Conformance is structural: a member may be defined
  in any mixin and `Store` satisfies the Protocol through inheritance. Nothing in this
  requirement names the module a method lives in. The summary lists each Protocol member with
  the mixin that defines it; that table is this task's input to the later decision the 29.5 ADR
  leaves open (composition instead of mixins).
- **The proxy's public surface IS the Protocol.** `_DaemonWriter` has no public method outside
  it, and the Protocol has no member the proxy lacks.
- **Standing rule: a later write method joins the Protocol in the change that adds it.** This is
  the checkable form of [[constitution#project-1]] (one writer, daemon-routed). Named by the
  reviews as coming: 23.1's `batch_transaction` and writer queue, `add_evidence_if_absent`,
  `add_memory(updated_at=)`, bug-185's bulk methods, 26.5's reroute, the 22.x ops. Those tasks
  add them; this task adds the rule and the test that enforces it (AC-16).
  - Scope of the rule: a write method that a CLI command or a verb can reach through
    `_store(write=True)` or the proxy. For such a method, joining means a Protocol member, a
    proxy method and a daemon op, together.
  - A write method that only the daemon's own op handlers call on the real `Store` never passes
    through the proxy. It does not become a Protocol member (the proxy could not honour it); it
    goes in the summary's member table marked daemon-only, so the next reader can see it was
    placed on purpose. This narrows the reviews' wording ("must include what these specs add")
    to what a Protocol shared with the proxy can mean; each of those tasks says which of the two
    its method is.
- `_store` is annotated `-> StoreWriter` and holds no `cast`. Both of its returns then have to
  type-check, which is mypy's proof that `Store` and `_DaemonWriter` both conform.
- **`_DaemonWriter.__getattr__` is removed.** It is what makes every attribute type-check and what
  hands an unmirrored mutation to a read-only replica.
- Reads that a command body mixes with writes go through ONE explicit member of the Protocol
  that returns a `Store` for reading: the store itself in-process, the lock-free replica under a
  daemon. The "no reader yet: run `rmx replica refresh`" error keeps its wording.
- The 5 parameter-list differences converge on `Store`'s signatures. A parameter the daemon op
  cannot carry is added to the op's payload or left out of the Protocol member; it is never
  accepted and dropped.
- `ingest_path` becomes a Protocol member that `Store` implements by delegating to
  `refmatrix.ingest.ingest_path`; `_ingest` loses its `isinstance` branch and the proxy keeps its
  progress stream inside its own method.
- **Each fall-through use is resolved as one of three**, in a table in the summary (the 35 of
  [[#measured-writer]], plus any mypy finds that the scan could not):
  - READ: goes through the reader member.
  - DAEMON-ABSENT MUTATION (the site runs only when no daemon exists): takes a `Store` from an
    accessor annotated `-> Store` that refuses when a daemon is up or busy, with the same
    classification `verbs.require_daemon` gives. It never receives the proxy.
  - MUTATION REACHABLE WITH A DAEMON UP: a bug row, and either a daemon op with a proxy method
    or a typed refusal. Not fixed silently inside this task's diff.
- No behaviour changes for a command whose daemon state does not change between its gate and its
  call.

### R6: no cast, and no new ignore {#r6}

- After this task there is no `typing.cast` call in `src/refmatrix`. The `Store._connect` cast
  becomes an `isinstance` narrowing with the same effect.
- A census test (AST, alias-aware: `from typing import cast`, `import typing`, `cast as c`) fails
  on any `typing.cast` call outside an allowlist of `module:qualname` entries, each with a
  reason. The allowlist is empty when this task lands. A method named `cast` on another object
  (the pyarrow call) is not flagged.
- The count of `# type: ignore` comments in `src/refmatrix` is a field of the baseline file and
  follows the same rule as a cell: it may only fall (5 at `f3709d2`).

## Acceptance criteria {#acceptance}

Each AC is a test that is RED at the task's start commit, unless marked (characterization).

- **AC-1: the gate fails on input that must fail.** A committed fixture tree
  (`tests/fixtures/type_gate/`: a strict module, a loose module, a config, a baseline) and one
  test per row. Each asserts the exact exit code and the named text:

  | case | planted | expect |
  |---|---|---|
  | F1 | the strict module returns an `int` from a function annotated as a bitmap-or-list (the bug-235 shape, no cast) | exit 1; the line names the file and `[return-value]` |
  | F2 | the strict module has one unannotated function | exit 1; `[no-untyped-def]` |
  | F3 | the loose module has 2 errors in a cell recorded as 1 | exit 1; names the cell, `2 > 1` |
  | F4 | a module with no cell has an error | exit 1 |
  | F5 | a cell recorded as 3 measures 2 | exit 3; `--update` writes 2; the next run exits 0 |
  | F6 | `--update` while another cell rose | exit 1; the baseline file is byte-identical |
  | F7 | a clean fixture | exit 0 (the control: the gate can pass) |

- **AC-2: a gate that did not run is not clean.** With a stand-in for mypy passed by parameter:
  it exits 2 with a traceback → gate exit 2; it prints one error line and `Found 0 errors` → 2;
  it reports `checked 0 source files` → 2; the baseline records another `major.minor` → 2, both
  versions named; the baseline records another duckdb version → 2. With the real mypy and a
  config whose strict section has a partial-wildcard pattern → 2, quoting mypy's line (at the
  start commit this shape runs to completion with the module un-strict). Without the stand-in:
  a Python that cannot `import mypy` → 2 with the `pip install -e '.[dev]'` remedy. None of these
  returns 0, 1 or 3.
- **AC-3: the repo's own configuration is strict where it says.** In a temp copy of
  `src/refmatrix`, one unannotated public function is appended to each strict module; the gate,
  run with the repo's `pyproject.toml` and baseline, exits 1 and names `[no-untyped-def]` once
  per strict module. This is the fixture that proves the real config, not the fixture config.
- **AC-4: the repo passes.** `./scripts/check-types.sh` exits 0 on the checkout; the suite test
  asserts exit 0 (never "not 2"; the bug-230 rule), and fails with the gate's own message
  otherwise.
- **AC-5: strict set and baseline agree.** A test enumerates the strict set from the tree
  (`rglob` under `src/refmatrix`: `verbs`, `query`, `handoff`, `mcp`, `store`, every
  `store_<concern>` module, and any other module 29.5's symbol map adds) and reads the
  `[tool.mypy]` overrides and the baseline: every enumerated module is in the overrides by its
  full name with all ten flags, and none has a baseline cell. Removing one flag from one module
  fails it; so does a new `store_<concern>.py` file that the overrides do not name.
- **AC-6: bug-235.** In a throwaway store: save `Count(Row(mentions, x))` and run it through the
  `rmx_matrix` verb (`action="run"`, `is_pql=True`) and through the MCP tool. Result:
  `{"shape": "int", "value": n}` with the right `n`; no `isError`. At the start commit this is
  `TypeError: 'int' object is not iterable`. `rmx matrix run --pql` prints `n`.
- **AC-7: a top-level non-result is an error.** `run_pql("foo")` raises `ValueError` starting
  `PQL:` and naming `foo`. At the start commit it returns the string `'foo'`.
- **AC-8 (characterization): the other shapes did not move.** Golden payloads recorded at the
  start commit for a `Row`, a `TopN` and an `ids_only` run through the daemon op, the verb and
  the CLI are equal after the change.
- **AC-9: the proxy has no fall-through.** `_DaemonWriter` defines neither `__getattr__` nor
  `__getattribute__`; `_store` contains no `cast`; `_store`'s return annotation is the Protocol.
- **AC-10: mypy enforces the Protocol.** In a temp copy of the tree, a command body that calls
  a `Store` method outside the Protocol on `_store()` (for example `rename_partition`) makes the
  gate exit 1 with `[attr-defined]`; removing one Protocol method from `_DaemonWriter` makes it
  exit 1 on `_store`'s return.
- **AC-11: the daemon-absent accessor refuses a live daemon.** In the sandbox, with a test daemon
  up, the accessor of [[#r5]] raises the typed busy / up refusal and opens nothing; with no
  daemon it returns a `Store`. One command per resolved class of [[#r5]]'s table is run both
  ways.
- **AC-12: the cast census.** The scanner finds every spelling in a synthetic module (direct,
  aliased import, `typing.cast`) and ignores a `.cast(` method call; on the tree it finds none.
  Before [[#r4]] to [[#r6]] land it finds 3.
- **AC-13: the ignore count only falls.** A sixth `# type: ignore` in a temp copy makes the gate
  exit 1.
- **AC-14: no regression.** The full suite is equal by E line before and after
  ([[feedback_compare_failures_by_error_not_name]]); the generated CLI tree and verb parity are
  unchanged.
- **AC-15: registry.** bug-235 is `fixed` with the sha, checked reachable from `master`
  ([[feedback_verify_fix_reachable_from_master]]).
- **AC-16: the proxy and the Protocol are the same set.** A test (AST, reading `Store` through
  its base classes as `census/census_writer_surface.py` does) asserts: the public methods of
  `_DaemonWriter` equal the members of `StoreWriter`; every member resolves on `Store` or one of
  its mixins. A public method added to the proxy alone fails it, which is how a later write
  method is made to join the Protocol.
- **AC-17: no mixin hides its host.** No strict module contains a `self` parameter annotated
  `Any`, and the count of `# type: ignore` in the store module family is 0. The gate's zero
  errors in every `store_<concern>` module is then a real check of cross-mixin calls. One planted
  call from a mixin to a method no host declares makes the gate exit 1 with `[attr-defined]`.

## Test strategy {#test-strategy}

RED first, by `@ch-test-engineer`, recorded to `workflow/review-output/`; GREEN by
`@ch-implementer`, who writes no tests ([[tdd-governance#pipeline]]).

- **Order of RED.** AC-1, AC-2 and AC-12 are RED because the script and the scanner do not exist;
  record the collection or import error as the red run. AC-6 and AC-7 are RED on behaviour. AC-9
  and AC-10 are RED on structure. AC-8 is characterization: its goldens are recorded first.
- **mypy inside the suite.** Each gate test passes a temp `--cache-dir`; tests that check the
  whole tree share one session-scoped cache so the second run is incremental. The gate is a
  child process of a sandboxed test: the RED run must show the child was not killed (the sandbox
  exits 86), and every test asserts the exact exit code.
- **No mocks of the unit under test.** The stand-in for mypy in AC-2 replaces an external tool
  and is recorded in `workflow/test_mock_registry.md`. The fixture tree in AC-1 runs the real
  mypy.
- **Mutations that must turn a named test RED** (planted on a commit that holds the fix; each
  must FAIL, not hang; `__pycache__` cleared after the batch):

  | mutation | must fail |
  |---|---|
  | the gate treats a missing cell as "no limit" | AC-1 F4, AC-3 |
  | the gate compares only the total error count | AC-1 F3 (one cell up, one down) |
  | exit 3 folded into exit 0 | AC-1 F5 |
  | `--update` writes rises too | AC-1 F6 |
  | the gate returns 0 when mypy's exit code is 2 | AC-2 |
  | the parsed-count check removed | AC-2 |
  | one strict flag dropped from one module in `pyproject.toml` | AC-5, AC-3 |
  | `run_pql` wraps a count as a one-element list | AC-6 |
  | the verb's count branch removed | AC-6 |
  | `__getattr__` restored on the proxy | AC-9 |
  | `_store` returns the proxy through a `cast` again | AC-9, AC-12 |
  | the accessor of [[#r5]] skips the daemon classification | AC-11 |
  | a config diagnostic line is ignored by the gate | AC-2 |
  | one `store_<concern>` module dropped from the overrides | AC-5 |
  | a public method added to `_DaemonWriter` only | AC-16 |
  | a mixin's `self` annotated `Any` | AC-17 |

- **The helper's own promises are mutated before the sites**
  ([[bsd-impressions#imp-convergence-tests-sites-not-helper]]): the gate's exit-code table and
  the baseline rules first, the call sites second.

## Files {#files}

Names after the 29.5 split are resolved by symbol ([[#split]]).

| file | change |
|---|---|
| `scripts/check-types.sh`, `scripts/check_types.py` | create: the gate |
| `scripts/type-baseline.json` | create: the recorded cells, mypy version, ignore count |
| `pyproject.toml` | `mypy>=2.4` in `dev`; `[tool.mypy]` and the strict overrides |
| `CLAUDE.md` | `#development-commands` and `#before-commit` |
| the modules that hold the symbols of `verbs`, `query`, `store`, `handoff`, `mcp` | annotations to zero errors |
| the module that holds `QueryEngine` and `_PQLEvaluator` | the result union; typed evaluator |
| the modules that hold `_op_query`, the CLI `query` and `matrix run` commands, the `rmx_matrix` verb | exhaustive dispatch; the count payload |
| `store.py` and the `store_<concern>` mixin modules | the declared host; `ingest_path`; the `isinstance` narrowing |
| a new leaf module in the store family | `StoreWriter` |
| the CLI module that holds `_DaemonWriter`, `_store`, `_store_rw`, `_ingest` (expected: `refmatrix/cli/__init__.py`) | Protocol return; no `__getattr__`; the daemon-absent accessor |
| the `cli/<group>_cmds.py` modules of the 35 fall-through sites | reader member or the accessor |
| `tests/test_type_gate.py`, `tests/fixtures/type_gate/` | create: AC-1 to AC-5, AC-13 |
| `tests/test_bug235_pql_count.py` | create: AC-6 to AC-8 |
| `tests/test_store_writer_protocol.py` | create: AC-9 to AC-12, AC-16, AC-17 |
| `tests/test_derive_graph_unchanged.py` | create: AC-18 |
| `workflow/bug_registry.md`, `workflow/test_mock_registry.md` | bug-235; the mypy stand-in |
| `workflow/implementation_summaries/task-29.2-mypy-gate.md` | the summary, with the before / after tables |

## Key decisions {#decisions}

None of these needs the user; each records the choice and why. The one that does is
`plan-29 D4` ([[#d4]]). A reviewer who disagrees with one below raises it as a new
`plan-29 D<n>` (D7 to D19 are taken by the 29.1 / 29.4 / 29.5 specs).

1. **Strict is per module, whole module**. The plan says "strict on the public API"; the
   user's D1 says "per-module strictness" ([[plan-29-code-quality#decisions]]). mypy cannot make
   only public functions strict, and a private helper returning `Any` defeats the public
   signature above it. Cost measured: 527 errors, 298 of them one mechanical kind. {#k1}
2. **A separate script, not a step of `lint-gmd.sh`**. Two scopes (docs, source), two
   failure modes, and one gate hiding another's crash is bug-230. {#k2}
3. **The count payload is `{"shape": "int", "value": n}`**. The daemon op returns it today
   and the CLI reads it; a second spelling for the verb would be the same value with two wire
   shapes. {#k3}
4. **Cells are (module, code) counts, and a stale cell fails (exit 3)**. A total lets a new
   error hide behind a fixed one; a line-keyed baseline rots on every edit; a stale cell that
   passes leaves slack for a regression. {#k4}
5. **The target is Python 3.10**, the declared floor: same 203 errors today, and it flags
   syntax or stdlib use the floor does not have. {#k5}
6. **`mypy>=2.4`, and the gate refuses another `major.minor`**. A new mypy can change the
   counts with no code change; that must arrive as its own commit, not as a red gate in someone
   else's. {#k6}
7. **The four result dispatches are not merged into one payload function**. Their
   payloads differ by design (the verb's weighted rows carry no `kind` / `path`); merging them
   changes wire shapes. The exhaustiveness check is the guard instead. {#k7}

## How this adapts to the 29.5 split {#split}

- Every site in this spec is a symbol name. File names and counts are those of `f3709d2` and are
  for tracing only. The census scripts walk `src/refmatrix` with `rglob`, find `_DaemonWriter`,
  `Store` and the cast sites by name in whichever module holds them, and read `Store`'s methods
  through its base classes (checked on a synthetic mixin tree).
- **The layout 29.5 produces** (from its author, 2026-11-14, and
  `plan-review-fable-2026-11-14-queue#b1`):
  - `refmatrix/cli/` is a package. Shared helpers stay in `cli/__init__.py` (`_store`,
    `_store_rw`, `_DaemonWriter` and `_ingest` are shared helpers today, so that is where this
    spec expects them); commands move to `cli/<group>_cmds.py`.
  - `store.py` stays and `Store` keeps its name and import path. Its methods move into mixin
    classes in `store_<concern>.py` modules that `Store` inherits. This is a file-size split, not
    a decomposition; an ADR written at 29.5's crucible records that.
- **First step of the task:** re-run `census/*.py` and the mypy runs at the start commit, and
  write the new tables into the summary. A count that changed for a reason other than moved code
  is a finding, reported before any edit. A mixin split can itself add errors (a mixin calling a
  method its class does not define); those are counted then, and fixed by [[#r2]]'s declared host.
- **The strict set after the split** is [[#r2]]'s: the five names, every `store_<concern>`
  module, and any module 29.5's symbol map shows now holds a symbol that lived in `verbs.py`,
  `query.py`, `store.py`, `handoff.py` or `mcp.py` at `f3709d2`.
- The CLI package is NOT strict; its modules get baseline cells. The 549 errors `cli.py` shows
  under `--strict` are not this task's work.

### What this task needs from 29.5 {#needs-295}

One acceptance criterion in 29.5's spec: its summary carries a table `symbol → old module → new
module` for every moved top-level class and function, and `refmatrix.store.Store`,
`refmatrix.query.QueryEngine` and `refmatrix.cli:cli_entry` stay importable under those names.
`plan-review-fable-2026-11-14-queue#b1` and its `#b2` already require 29.5 to publish that map
and to keep `Store`'s import path. The AC text was sent to 29.5's author on 2026-11-14
([[bsd-pattern-handoff-without-sibling-ac#rule]]); until 29.5's spec is merged it is requested,
not confirmed. Without the table this task derives the strict set from `git log --follow`, which
is slower but not blocked.

## The seam with 29.3 {#seam}

Both tasks edit the query module and `handoff`. They are not parallel there
(`plan-review-fable-2026-11-14-queue#p29-4`). Order for the shared symbols:

| step | task | what | why in this place |
|---|---|---|---|
| 1 | 29.3 (a) | `run_git` adopted in `handoff`, `sync`, `store`, `upgrade`, the CLI | removes git wrappers before they would be annotated |
| 2 | 29.3 (b) | term resolution, PQL argument kinds, the evaluator's value type | the query half first: its behaviour changes are settled before the module is frozen under strict flags |
| 3 | 29.2 [[#r4]] | the `run_pql` result union, on the value type step 2 defined | closes bug-235 on the final evaluator |
| 4 | 29.2 [[#r2]] | the strict pass over the five surfaces and the mixin modules | annotates the final shape of the query module and `handoff` |
| 5 | 29.3 (c) | the broad-except triage inside the strict modules | last, so it does not collide with step 4 |

Rules for both tasks:

- A module 29.3 creates (`gitrun`, `deadline`) has no baseline cell. The gate has not landed
  when 29.3 creates them, so 29.3 proves `mypy --strict` clean on each by a direct run.
- Once the gate has landed, every 29.3 commit passes it; a fall in a cell is committed with
  `--update`.
- 29.3's other slices (d to h) touch no strict module's public surface and may land on either
  side of step 4.
- If the steps cannot be kept in this order, the later task rebases; neither task relaxes a
  requirement to avoid a conflict.

## Edits that change the derive hash {#derive-hash}

`store.derive_code_hash` hashes the CONTENT of the modules in `_DERIVE_PASS_MODULES`
(`ingest.py` for the `ingest` and `semantic` passes, `ingest_gmd.py` for `gmd`,
`session_ingest.py` and `ingest_gmd.py` for `sessions`), and `store.py` is in the no-argument
union. An annotation added to `ingest.py` to satisfy a strict module's `no-untyped-call`, or a
comment added by 29.3(c), changes that hash. After the next deploy every fleet store then reads
`behind_code` for those passes although nothing about what is derived has changed. 29.5 changes
the same lists when it moves files.

- This task keeps its edits to those modules to what a strict module's error requires, lists
  each in the summary, and lands them in ONE release together with 29.3's edits to the same
  files.
- **AC-18: the derived graph did not move.** On a throwaway store built from a fixed fixture
  tree, the graph digest (entities, concepts, linkage bitmaps, evidence) derived at the start
  commit equals the one derived at the end commit. This is the evidence that the flip is a
  false positive.
- What is done about the flip on live stores is `plan-29 D4` ([[#d4]]). No agent re-stamps or
  re-derives a live store.

## Open decision for the user {#open-decisions}

**plan-29 D4: the fleet-wide `behind_code` flip from annotation- and comment-only edits.** {#d4}

29.2 and 29.3 edit `ingest.py`, `ingest_gmd.py` and possibly `session_ingest.py` without
changing what they derive ([[#derive-hash]]). Options:

- (a) Accept the flip and re-derive every store (`rmx reingest`) after the release. Cost: a full
  re-derive per store for no change in the graph.
- (b) Accept the flip and have the lead re-stamp each store through the existing derive-stamp
  path, announced and backed up first, with AC-18's equal digest as the evidence. No re-derive.
- (c) Change `derive_code_hash` to ignore comments and annotations. That is a change to the
  staleness detector, flips every store once by itself, and belongs with whatever 29.5 decides
  for the same hash.

Recommended: (b), in one release that carries all such edits from 29.2, 29.3 and, if it lands
close enough, 29.5. It is the user's call because it is a write to every live store's stamps.
If 29.5's own decision on this hash covers annotation-only edits, D4 is settled by it.

## Review findings folded on 2026-11-14 {#fold}

The review documents are `workflow/plan-review-fable-2026-11-14-queue.md` (master `3551894`) and
`workflow/plan-review-fable-2026-11-14-store.md` (master `ec3e0e8`). They landed on master after
this branch's base (`f3709d2`), so they are cited here as `doc-id#anchor` code spans; a wikilink
to a document this branch does not hold fails the repo lint. Turn them into wikilinks in the
merge commit. {#fold-cites}

| finding | change here |
|---|---|
| `plan-review-fable-2026-11-14-queue#b1`: `Store` becomes mixin classes | [[#r2]] (each `store_<concern>` module strict, by name; one declared host), [[#r5]] (structural conformance, leaf module, member-by-mixin table), AC-5, AC-16, AC-17, [[#split]] |
| `plan-review-fable-2026-11-14-queue#p29-4`: the writer Protocol is the checkable form of Constitution VII; every later write method joins | [[#r5]] standing rule, AC-16 |
| `plan-review-fable-2026-11-14-store#plan29-converge-candidates`: the Protocol must include what T4-T6 specs add | [[#r5]] names them; AC-16 makes joining mandatory |
| `plan-review-fable-2026-11-14-queue#p29-4`: not parallel on the query module; 29.3's query half first | [[#seam]], [[#r4]] |
| `plan-review-fable-store D5`: dev venv duckdb 1.5.2 below the 1.5.3 floor | not settled here; [[#measured-duckdb]], [[#r3]] (the baseline names the duckdb version), AC-2 |
| 29.5's author: `derive_code_hash` hashes file content; layout of the split | [[#derive-hash]], AC-18, `plan-29 D4`; [[#split]] |

## Out of scope {#out-of-scope}

- Strict typing of the CLI package, `daemon`, `hub` or any module outside the strict set. They
  only may not get worse.
- `TypedDict` results for verbs. `dict[str, Any]` is accepted in a strict signature.
- A ruff or formatter gate ([[plan-29-code-quality#non-goals]]).
- Static checking between the MCP adapter and the verbs it dispatches to by name; the verb
  parity test covers that.
- One payload function for all query results ([[#k7]]).
- bug-236, bug-237 and the rest of bug-238: [[task-29.3-converge-shapes#slice-b]] and the
  registry.
- Stubs for `scipy` (the one `import-untyped` error): it stays in its module's baseline cell.
