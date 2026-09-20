---
gmd: "0.1"
id: task-13.3-surfaces-and-parity
title: "Task 13.3: CLI and MCP adapters over the sweep verb, parity asserted"
tags: [task, plan-13, cli, mcp, verbs]
metadata:
  node_type: task
  status: pending
  plan: plan-13-cross-partition-sweep
---

# Task 13.3: surfaces and parity {#root}

> Plan: [[plan-13-cross-partition-sweep]]
> Status: Pending
> Depends on: [[task-13.1-sweep-verb]]

rel: part-of -> [[plan-13-cross-partition-sweep]]
rel: depends-on -> [[task-13.1-sweep-verb]]
rel: reinforces -> [[project_verbs_layer_antidrift]]

## Requirements {#requirements}

- `rmx sweep` (CLI) and `rmx_sweep` (MCP) are ADAPTERS: argument parsing and rendering only. The
  plan-3 finding stands as the warning — "every verb has a CLI command that calls it" was an
  existence check, and 26 of 28 twins never called the verb (`bsd-plan3-verbs-parity-8ba4799#bs-1`).
  The test asserts the twin CALLS the verb over its full parameter set, not that a command exists.
- The MCP schema is GENERATED from the verb signature, never hand-written.
- Rendering shows, per row: the partition it came from and its `also_in` provenance. A union whose
  output cannot say which partition answered is not usable as a diagnostic surface.
- The per-leg block (`legs[]`) renders on `--verbose` and is always present in `--json`.
- `console.print` is NOT used for any output containing `[[wikilinks]]` — rich parses them as markup
  and silently deletes them, and the GMD linter reports 0 errors on the damaged output
  (`project_bsd_three_round_arc_plans_7_10#r3`). `click.echo` for those paths.

## Acceptance criteria {#acceptance}

- The verb-parity test covers `sweep` over its FULL parameter set (deadline, fusion arm, per-leg
  caps, include/exclude legs).
- `rmx sweep --json` and the MCP tool return the same structure for the same arguments against the
  same store.
- `rmx sweep` on a store with one partition returns that partition's rows and a `legs[]` naming the
  empty legs — it degrades, never errors.

## Files {#files}

- modify `src/refmatrix/cli.py` (the `sweep` command)
- modify `src/refmatrix/mcp.py` if the tool list is not fully generated
- modify `tests/test_verbs_parity.py` (or the existing parity test file, confirmed at write time)
- create `tests/test_sweep_surfaces.py`

## Test strategy (RED first) {#test-strategy}

1. `test_cli_sweep_calls_the_verb` — patch the verb, assert the CLI path reaches it with every
   parameter forwarded (the anti-existence-check test).
2. `test_mcp_sweep_calls_the_verb` — same, through the MCP dispatcher.
3. `test_mcp_and_cli_return_the_same_json` — one store, one query, byte-compare.
4. `test_rows_name_their_partition_and_provenance` — rendering contains both.
5. `test_wikilink_bearing_output_survives_rendering` — a row whose snippet contains `[[name]]`
   still contains it after render (the `console.print` regression guard).
6. `test_single_partition_store_degrades_with_named_empty_legs`.

**Mutations:** hand-write the MCP schema so it drifts from the signature (kills 1/2 via parity);
render with `console.print` (kills 5).
