---
gmd: "0.1"
id: plan-29-spec-census
title: "Plan-29 spec census: the scripts behind the numbers in task specs 29.1, 29.4 and 29.5"
tags: [measurement, plan-29, tests, cli, store, registry, census]
metadata:
  node_type: measurement
  created: 2026-11-14
  updated: 2026-11-14
---

# Plan-29 spec census {#root}

The scripts that produced the measured numbers in the three task specs, run at `f3709d2` on
2026-11-14. Every one is a static read of the tree, except `click_tree.py`, which imports
`refmatrix.cli` to walk the real click tree. None runs a test, opens a store or calls `rmx`.
Each task's R0 runs them again at its base sha. {#what}

rel: evidence-for -> [[task-29.1-registry-triage]]
rel: evidence-for -> [[task-29.4-suite-health]]
rel: evidence-for -> [[task-29.5-split-giant-modules]]

## How to run {#run}

From a scratch directory (several scripts write a `.json` beside them for the next one), with
`R` the checkout. `collect.log` is the output of
`PYTHONPATH=$R/src $R/.venv-eval/bin/python -m pytest --collect-only -q -p no:cacheprovider`.

| Script | Arguments | Output committed as (`workflow/review-output/`) | Spec |
|---|---|---|---|
| `registry_count.py` | `$R/workflow/bug_registry.md` | `plan29a-registry-count.log` | 29.1 |
| `suite_census.py` | `$R collect.log census.json` | file, line and import fan-in totals quoted in 29.4 | 29.4 |
| `wallclock_census.py` | `$R` | `plan29a-wallclock-census.log` (first part) | 29.4 |
| `wallclock_nonliteral.py` | `$R` | `plan29a-wallclock-census.log` (second part) | 29.4 |
| `tier_signals.py` | `$R collect.log <wallclock log> tiers.json` | writes `tiers.json` | 29.4 |
| `tier_rule.py` | `$R tiers.json <wallclock log>` | `plan29a-tier-census-v3.log` | 29.4 |
| `family_census.py` | `$R` | `plan29a-family-census.log` | 29.4 |
| `click_tree.py` | `$R` (run with `PYTHONPATH=$R/src` and the dev interpreter) | `plan29a-click-tree.log`; writes `clicktree.json` | 29.5 |
| `cli_map.py` | `$R` (needs `clicktree.json`) | `plan29a-cli-map.log`; writes `cli_assign.json` | 29.5 |
| `store_census.py` | `$R` | `plan29a-store-census.log` | 29.5 |
| `private_census.py` | `$R` | `plan29a-private-census.log` (first part); writes `private.json` | 29.5 |
| `private_map.py` | none (reads `private.json`, `cli_assign.json`) | `plan29a-private-census.log` (second part) | 29.5 |
| `citation_census.py` | `$R` | `plan29a-citation-census.log` | 29.5 |
| `cli_refs.py` | `$R` (dev interpreter, for `sys.stdlib_module_names`) | `plan29a-cli-refs.log` | 29.5 |
{#run-table}

`plan29a-tests-per-file.log` is the collection listing reduced to one count per file, with the
collector's own total as its last line. `plan29-spec-wallclock-census.log` is the first
draft's grep count (53 asserts in 21 files), kept because 29.4 quotes it beside the syntax-tree
count (78 in 26). {#run-notes}

## Limits {#limits}

- The signal tables in `tier_signals.py` are regular expressions over source text. They are a
  draft of the rule that 29.4 R1 turns into `tests/tiering.py`, where calls are matched on the
  syntax tree.
- `cli_map.py` assigns a helper to a command module when every def that names it is in that
  module, and to the core otherwise. It resolves names, not attribute chains, so a helper used
  only through `getattr` would be put in the core.
- `store_census.py`'s per-concern table is a name match and is rough; the spec's store map uses
  the section banners in `store.py`, by line number.
{#limits-list}
