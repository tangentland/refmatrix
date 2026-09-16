---
gmd: "0.1"
id: task-8.2-summary
title: "Task 8.2/8.3 summary: brief surfaces and the GMD index"
tags: [implementation-summary, plan-8]
metadata:
  node_type: summary
  task: task-8.2-plan-8-derived-coverage-notes
  created: 2026-09-15
---

# Task 8.2 + 8.3 summary {#root}

rel: realizes -> [[task-8.2-plan-8-derived-coverage-notes]]
rel: realizes -> [[task-8.3-plan-8-derived-coverage-notes]]
rel: part-of -> [[plan-8-derived-coverage-notes]]
rel: depends-on -> [[project_verbs_layer_antidrift]]

## What shipped {#shipped}

`rmx memory brief` on all three surfaces, plus the GMD index and its parser.

- **verb** — `rmx_memory` gains a `brief` action with `min_members`, `min_dates`,
  `min_mentions`, `classes`, `save`, `plan`. The MCP tool picks all six up from the generated
  schema; nothing was hand-written there.
- **daemon** — `_op_memory_brief`. Derivation runs through `_read_with_fallback`; `save=True`
  takes `_store_lock` and writes one memory row per brief in the `brief/<class>` namespace.
- **CLI** — `rmx memory brief` with `--class`, `--compile`, `--save`, `--gmd`, `--json`,
  `--limit`. Rendering only; it calls `verbs.memory` and constructs no `Store`.
- **index** — `brief.render_gmd` / `brief.parse_gmd`.

## The split, and why it matches compile {#split}

`memory compile` keeps its clustering in the CALLER because that pass reads the whole vector
matrix and a fat daemon is the process jetsam kills; only the apply half is an op, and the plan
travels as data. Brief derivation is genuinely cheap — two decoded linkage fragments and two small
SQL queries — so it runs in the op on the read path. When the plan-derived classes are wanted,
`--compile` runs the clustering CLI-side and the plan travels to the op exactly as
`memory_compile_apply` already takes it. The expensive pass never moved into the daemon.

A class that could not run reports why (`classes_not_run`, printed in yellow). A class that did
not run is not a class that found nothing.

## The index contract {#index}

`render_gmd` sorts by `(class, label)`, so two runs over one store produce identical bytes — a
derived file that churns every run is a file nobody keeps in git. `parse_gmd` recovers what it
wrote, which is the round trip `consolidate` states as the contract: the index is regenerable from
the store and the store is rebuildable from the index.

The edge verb is `evidence-for`, pointed from the index at each cited memory, because the memory
SUPPORTS the finding. `consolidate.render_gmd` records the sibling mistake it had to avoid —
emitting a container's own inverse verb would have claimed the subject is part of its own members.

An evidence id with no resolvable name is not emitted as a `rel:` (that would be a dangling edge)
but stays visible in both carriers, and the evidence COUNT never shrinks. "Three memories agree"
and "three memories, one of which I could not find" are different claims.

## Tests {#tests}

22 tests: `tests/test_brief_surfaces.py` (11), `tests/test_brief_gmd.py` (11).

- RED: `workflow/review-output/red-task-8.2.log`, `red-task-8.3.log`
- GREEN: `workflow/review-output/green-task-8.3.log`

Parity is compared over the full brief parameter set **with the compared-key count asserted**,
because plan-3's parity test compared zero of `memory_recall`'s parameters and hid a `k` default
mismatch behind a green run ([[impression_bsd_existence_check_tests]]).

Nine mutants killed. **Three initially SURVIVED and were real test weaknesses, now fixed:**

| Surviving mutant | Why the test was weak | Fix |
|---|---|---|
| render not order-stable | the fixture had one brief per class, so class grouping normalised the shuffle before the sort could be tested | fixture now puts three briefs in ONE class and asserts the emitted label order |
| unresolved-id note dropped | the inline evidence line also carried the id, so the note could be deleted alone | each carrier asserted separately |
| unresolved id erased from the evidence line | the note also carried it — the two masked each other | same; plus the evidence COUNT is asserted not to shrink |

That masking pair is the [[impression_bsd_faked_wire_field]] shape in miniature: two readers of one
fact, neither individually pinned, so either could be removed with the suite still green.

## Two test-fixture bugs found on the first run {#fixture-bugs}

Not code defects, recorded so the next author does not re-derive them: `supersedes` needs an
explicit `add_linkage_type` (only some verbs are pre-registered), and `add_concept` canonicalises
`fast-exit` to `fast_exit`, so an assertion must read the stored name back rather than the string
the caller typed.
