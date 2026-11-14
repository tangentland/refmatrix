---
gmd: "0.1"
id: impl-bug-241-reingest-gmd-pass
title: "bug-241: markdown reaches the GMD pass on every code+docs ingest, tldr cache or not (implementation summary)"
tags: [implementation-summary, bug-241, bug-216, gmd, ingest, reingest]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-14
---

# bug-241: markdown reaches the GMD pass on every code+docs ingest {#root}

rel: derives-from -> [[bug_registry]]
rel: related-to -> [[impl-task-bug216-rule-docs-in-graph]]

Branch `task-bug241-rule-docs-gmd-on-reingest`, base master `78c0c11` (0.83.0). RED by red-216
at `a2ac833` (+ mutation logs `8f99332`): `tests/test_bug241_rule_docs_reingest.py`, 28 RED /
68 pass. GREEN `b1bc9d1` (src only, `src/refmatrix/ingest.py`). No test edited. {#commits}

## Cause {#cause}

Measured by red-216 (`bug241-trace.log`): `ingest._ingest_path_inner` ran `_ingest_tree` only
`if source in ("auto", "tree") and n == 0`, and `_ingest_tree` was the ONLY code+docs pass that
routed markdown to `ingest_gmd_paths`. With `.tldr/cache/semantic/metadata.json` or
`call_graph.json` (the live refmatrix tree has both) the tldr pass answered first, so `rmx ingest`
and `rmx reingest --force` GMD-parsed no markdown at all: the rule docs stayed plain relpath rows
with no anchors, bug-216's repair-by-reingest was a no-op live, and the reingest's coverage line
said "never stamped: gmd". The RED fails exactly on the reingest route with a cache (metadata or
call graph, fresh or with a prior plain row); the sync route and the no-cache tree were already
right. {#cause-text}

## Fix {#fix}

- **One routing.** `_ingest_markdown_gmd(s, root, *, ignore_root=None)` is THE code+docs routing
  of markdown to the GMD pass: every `GMD_EXTS` file under `root` that `should_ignore` keeps
  (judged against `ignore_root`, the project root — the same predicate every walker uses), a
  legacy relpath `doc` row purged first (guarded on its existence, as before), one batched
  `ingest_gmd_paths(..., lenient=True, project_root=root)`. Returns the docs ingested.
  {#fix-helper}
- **Both callers.** `_ingest_tree` no longer collects markdown in its walk; it calls the helper
  once at the end (its walk still goes through `should_ignore`, as bug-216 R2 pins).
  `_ingest_path_inner` calls the helper whenever the tree pass did NOT run — a tldr metadata or
  call-graph cache answered, or `--source` was explicit — so markdown is GMD-routed exactly once
  per ingest, whichever primary source answered. {#fix-callers}
- **`--source metadata|tldr|graphify` (explicit).** Markdown is still GMD-routed. `source` chooses
  where CODE structure comes from; none of those sources covers markdown, and every other markdown
  pass in `_ingest_path_inner` (ADR, plain markdown records) already runs for every `source`.
  Skipping the GMD routing under an explicit source would recreate this bug for anyone who passes
  one. `source=tree` and `auto` with no cache are unchanged (the tree pass routes). Code semantics
  of `source=` are untouched. {#fix-source}
- **The gmd stamp.** `ingest_gmd_paths` stamps the `gmd` derive pass when it runs, so a cached
  tree now gets it. Probe (`bug241-stamp-probe.log`): `rmx reingest --force --no-sessions
  --no-embed` on the RED's metadata-cache shape leaves `derive_stamps` = gmd, ingest, pagerank,
  semantic, and the coverage line reads only `derive coverage[proj]: skipped this run: embed` — no
  `never stamped: gmd`. {#fix-stamp}
- **The failure fallback is loud now.** The GMD pass's `except` (registering the files as plain
  docs) used to swallow the error and a nested `except: pass`; it now prints the error and counts
  every file it could not register (stderr). It moved into the helper, so it is this change's
  code. {#fix-loud}

## Out of scope, touched or not {#out-of-scope}

The plain relpath `doc` row that coexists with the GMD doc row (red-216's side measurement; live
`docs/SYSTEM.md` + `refmatrix/SYSTEM`) is NOT changed. This fix keeps the existing behaviour: the
helper purges a legacy relpath row before the GMD pass, as `_ingest_tree` always did, and the
later plain markdown pass (`_build_markdown_record`) still runs for every changed markdown file,
re-creating a relpath row — on the cached path now exactly as on the tree path. {#out-of-scope-text}

## Runs {#runs}

Absolute `PYTHONPATH=/Volumes/littlebig/refmatrix-bug241/src`; logs in `workflow/review-output/`:

- `tests/test_bug241_rule_docs_reingest.py`: **96 passed** (`bug241-green-iter1.log`).
- The bug-216 family + the ingest / gmd / reingest / sync / watch / derive / workflow_ignore files
  (+ memory_bridge, bug179, session_ingest, verb_parity, docs_generated): **795 passed**
  (`bug241-family.log`).
- Full suite at `b1bc9d1` (`bug241-full.log`): **18 failed, 4978 passed, 1 skipped**, against
  `release-0.83.0-full.log`'s 14 failed, by E line:
  - 14 in `tests/test_bug240_ingest_file_arg.py` / `test_bug240_ingest_file_arg_mcp.py`: bug-240's
    RED, committed onto this branch by another agent during the run (`36341f5`, `7145c19`, on top
    of `b1bc9d1`); RED by design, not this change.
  - `test_catalog_measure::test_rewrite_bytes_is_the_median_of_the_runs` (`KeyError:
    'rewrite_bytes_all'`): not in the baseline run; passes alone at `b1bc9d1` AND at the base
    `78c0c11` (30 passed each, `bug241-catalog-measure-{tip,base}.log`) — load-dependent, not this
    change.
  - `test_brief_real_daemon` (DuckDB lock conflict) and `test_task21_1_agent_usage_report` ×2:
    same E lines as 0.83.0.
  - The baseline's `test_plan4_remedy`, `test_repo_hooks_in_sync` and `test_search_hooks` ×9
    failures did not recur.

{#runs-list}

## Mutations {#mutations}

Each alone in a throwaway clone of `b1bc9d1`, restored with `git checkout -- src` in its own
command, `__pycache__` cleared; suite = the bug-241 file:

| mutation | result | log |
|---|---|---|
| restore the `n == 0` gate for markdown (the cached path skips the helper) | 28 failed | `bug241-mut-n0-gate.log` |
| route markdown around `should_ignore` | 12 failed | `bug241-mut-no-ignore.log` |

{#mutation-table}

## Next {#next}

AC-6 live: after deploy, the lead re-runs bug-216 R4's `rmx reingest --force --no-sessions` and
`scripts/check-rel-landing.py` on a fresh read-only copy (bug-216 #ac-6). {#next-text}
