---
gmd: "0.1"
id: impl-remedy-plan-7-10-r4
title: "Remedy — ch-bsd r4, plans 7-10"
tags: [implementation, remedy, bsd, plan-7, plan-8, plan-9, plan-10]
metadata:
  node_type: implementation-summary
  status: complete
  date: 2026-09-16
---

# Remedy — ch-bsd r4, plans 7-10 {#root}

All ten r4 findings closed on branch `bsd-r4-remedy` off `master` at `05bef34`.

rel: implements -> [[bsd-plan7-10-r4-05bef34]]
rel: derives-from -> [[bsd-plan7-10-r3-4f451c5]]

Rounds 1-3 have no implementation summary — `f3c23b1`, `4f451c5` and `6b6a610` went in as bare
`fix(bsd-rN)` commits — so this is the first summary in the lineage and there is no earlier one to
amend.

## What changed {#changes}

| finding | fix | file |
|---|---|---|
| `#b-1-r4` | pass `stats=stats` to `render_gmd` | `src/refmatrix/cli.py` |
| `#b-2-r4` | delete the stray fence; add `eval/` to lint scope; teach the linter to report an unclosed fence | `eval/production/longmemeval/REPORT.md`, `scripts/lint-gmd.sh`, `tools/gmd/lint.py` |
| `#s-1-r4` | first CLI test of `memory compile --out -` | `tests/test_plan7_10_remedy_r4.py` |
| `#s-2-r4` | `singleton` returns its own reason key; `compile_briefs` MERGES both detectors' reasons | `src/refmatrix/brief.py` |
| `#s-3-r4` | assertions on the two buckets that were deletable green | `tests/test_plan7_10_remedy_r4.py` |
| `#s-4-r4` | mock registry rows 68 + 72 corrected (file lists, second symbol, renamed fake) | `workflow/test_mock_registry.md` |
| `#m-1-r4` | real-timestamp rule for ledger artifacts; r3's forward-dating annotated in place | `.claude/agents/ch-bsd.local.md`, `workflow/bullshit/INDEX.md` |
| `#m-2-r4` | bug-033 opened for the ~8.5 s gap; handoff repointed off the `fixed` bug-031 | `workflow/bug_registry.md`, `handoff.md` |
| `#m-3-r4` | bug-034 registers the five stable suite failures | `workflow/bug_registry.md` |
| `#m-4-r4` | `conftest.source_of` slices by NAME from disk; both `inspect.getsource` sites converted; guard test blocks reintroduction; bug-035 | `tests/conftest.py`, `tests/test_plan4_remedy_r2.py`, `tests/test_brief_surfaces.py` |

## The one that matters {#the-one}

`#b-2-r4` is the finding worth remembering, because the linter could not have caught it and now
can. A `{#anchor}` is a graph node; both parsers that matter toggle on code fences; so an UNCLOSED
fence deletes every node after it while the linter reports zero errors — it has been told the rest
of the file is code. `tools/gmd/lint.py` now emits `unclosed-fence` as an error naming the line the
fence opened at. Repo-wide after the fix: **0 unclosed fences**. {#unclosed-fence}

The second half is scope. `eval/` is a corpus root, so its GMD docs are INGESTED into the graph,
but it was not in `scripts/lint-gmd.sh` — ingested and ungated. Adding it costs **0 new errors**
(seven `no-gmd-version` warnings on plain-markdown READMEs, which are informational). {#lint-scope}

## TDD record {#tdd}

RED `workflow/review-output/pytest-r4-remedy-red.log` — **7 failed, 6 passed**. The six that passed
on the first run are guard tests, and that is the honest reading of those findings: `#s-1-r4`,
`#s-3-r4` and half of `#s-2-r4` were **untested**, not broken. A test written for an untested
behaviour passes immediately; claiming it as RED would be theatre.

GREEN `workflow/review-output/pytest-r4-remedy-green.log` — **127 passed** across
`test_plan7_10_remedy_r4`, `test_brief_detectors`, `test_brief_surfaces`, `test_brief_gmd`,
`test_brief_bsd_r1`, `test_memory_compile`, `test_plan4_remedy_r2`.

Six mutations, each run, each killing at least one test: {#mutations}

| mutation | result |
|---|---|
| M1 drop `stats=stats` | `test_cli_gmd_headline_carries_the_memory_count` fails |
| M2 drop `eval/` from lint SCOPE | `test_lint_scope_covers_every_corpus_root_carrying_gmd` fails |
| M3 restore the stray fence | 2 fail, incl. the store's own parser losing `#next` |
| M4 drop `by_reason` from `singleton` | 2 fail, incl. the pre-existing detector test |
| M5 revert `source_of` → `inspect.getsource` | the guard test fails |
| M6 remove the `unclosed-fence` check | `test_linter_reports_an_unbalanced_fence` fails |

## Not fixed, and named {#not-fixed}

`./scripts/lint-gmd.sh` reports **103 errors**, unchanged by this branch. Every one is a dangling
`bsd-impressions#imp-*` anchor in an older `workflow/bullshit/` report, left by a consolidation that
replaced ~35 anchors with `{#imp-consolidated-0914}` and recorded the old ids in prose as
"Former anchors: …". The mapping to repair them exists; the repair is a ledger curation pass, not
part of this remedy, and `CLAUDE.md#before-commit` has not been green for days. Stated rather than
absorbed. {#lint-debt}

rel: related-to -> [[bug_registry#registry]]
