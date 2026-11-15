---
gmd: "0.1"
id: plan-31b-spec-census
title: "Plan-31 spec census (31.1, 31.6, 31.2): the scripts behind the numbers in the three task specs"
tags: [measurement, plan-31, gmd, frontmatter, resolver, learned-rows, evidence, census]
metadata:
  node_type: measurement
  created: 2026-11-15
  updated: 2026-11-15
---

# Plan-31 spec census: 31.1, 31.6, 31.2 {#root}

The scripts that produced the measured numbers in three task specs, run on 2026-11-15 at
`f3a508f` with the dev tree's `.venv-eval`. Each task's R0 runs its scripts again at its base
sha. {#what}

rel: evidence-for -> [[task-31.1-frontmatter-type-refusal]]
rel: evidence-for -> [[task-31.6-one-wikilink-resolver]]
rel: evidence-for -> [[task-31.2-learned-evidence-agreement]]
rel: related-to -> [[plan-31-pre-mod-loose-ends]]

## What each one touches {#touches}

None opens a live store, starts a daemon or calls `rmx`. {#touches-rule}

| Script | Reads | Writes |
|---|---|---|
| `frontmatter_census.py` | markdown files of the roots and memory dirs passed, through the ingester's `_parse_frontmatter` | nothing |
| `frontmatter_probe_a.py`, `frontmatter_probe_b.py` | nothing outside their own fixtures | a throwaway store under a short `mkdtemp` root in `/tmp`, removed at the end |
| `resolver_census.py` | the files of the scope passed, through `tools/gmd/lint.py` and `parse_gmd` | nothing |
| `corpus_diff.py` | the same, plus the project root walked as the ingest walks it | nothing |
| `resolver_landing.py` | a **copy** of `catalog.read.duckdb`, opened `read_only=True`, and `resolver_census.py`'s `--lines` output | nothing |
| `orphan_census.py` | a **copy** of `catalog.read.duckdb`, opened `read_only=True`, and the project's files | nothing |
| `resolvable_split.py` | the same copy, and a stat of each file a learned orphan names | nothing |
{#touches-table}

The catalog copy is made by hand first (`cp <project>/.refmatrix/catalog.read.duckdb
<scratch>/`), never inside a checkout. The scripts refuse nothing about the path they are
given, so the caller passes the copy. {#touches-copy}

## How to run {#run}

With `R` the checkout, `P` the project whose store and files are measured (the dev tree),
`M` its Claude memory dir and `C` the catalog copy. The resolver scripts are run with `P` as
the working directory, with `scripts/lint-gmd.sh`'s scope.

| Script | Arguments | Output committed as (`workflow/review-output/`) | Spec |
|---|---|---|---|
| `frontmatter_census.py` | `<repo root>… --memory-dir <dir>…` | `spec31b-frontmatter-census.log` (repo names only; `--paths` output is not committed) | 31.1 |
| `frontmatter_probe_a.py`, `frontmatter_probe_b.py` | none | `spec31b-frontmatter-probe.log` | 31.1 |
| `resolver_census.py` | `CLAUDE.md docs/ workflow/ eval/ .claude/PROJECT_PROFILE.md --memory-dir M [--lines]` | `spec31b-resolver-census-refmatrix.log`; per fleet repo (whole root, counts only) `spec31b-resolver-census-fleet.log` | 31.6 |
| `resolver_landing.py` | `C <the --lines output> P` | `spec31b-resolver-landing-refmatrix.log` | 31.6 |
| `corpus_diff.py` | `P CLAUDE.md docs/ workflow/ eval/ .claude/PROJECT_PROFILE.md --memory-dir M` | `spec31b-corpus-diff-refmatrix.log` | 31.6 |
| `orphan_census.py` | `C P` | `spec31b-orphan-census-refmatrix.log` | 31.2 |
| `resolvable_split.py` (plan-31 D14's match rule) | `C P` | `spec31b-resolvable-split-refmatrix.log` | 31.2 |
{#run-table}

## Limits {#limits}

- The fleet rows of the resolver census walk each repo's whole root, not that repo's own lint
  scope, so vendored and duplicated trees are counted. They are an upper bound, good for
  proportions. {#limit-fleet}
- `resolver_census.py` cannot see a store: a bare link that no doc owns may still bind a
  same-named concept in a live store. It counts that as a miss; `resolver_landing.py` shows
  where such lines landed. {#limit-store}
- `orphan_census.py`'s `verifies` is a literal substring test on the recorded line, with a
  regex count beside it. The product's own rule (`store.verify_evidence_rows`) also bridges
  identifier spellings, so the product may serve a few more rows than counted. {#limit-verify}
- Two more reads behind the specs were one-off queries on the same catalog copy and are not
  scripts here: the 136 evidence-less edges on the `rel:` verbs (31.6), and the statement
  times of the evidence deletes on a writable scratch copy, rolled back (31.2). Each task's
  R0 repeats them and commits the query with its output. {#limit-one-off}
- The dev tree moved during the day: the lint scope held 1,153 GMD docs at the first run and
  1,168 at the last. Numbers in a spec name the run they came from. {#limit-moving}
