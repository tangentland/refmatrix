---
gmd: "0.1"
id: impl-task-t0-5-plan8-remedy
title: "T0.5 GREEN: the plan-8 remedy (brief is verb-first, the GMD -> store half deleted)"
tags: [implementation-summary, t0, t0-5, plan-8, brief, verbs, mcp, parity]
metadata:
  node_type: implementation-summary
  status: green
  created: 2026-11-19
---

# T0.5 GREEN: the plan-8 remedy {#root}

rel: implements -> [[task-t0-suite-trust-sweep#t0-5]]
rel: implements -> [[plan-6-deferrals-docs-benchmark#q1]]
rel: amends -> [[plan-8-derived-coverage-notes#proposed-approach]]
rel: depends-on -> [[self-audit]]
rel: supersedes -> [[task-8.3-plan-8-derived-coverage-notes]]
rel: derives-from -> [[bsd-t05-r1-61b0666c]]

Branch `task-t0.5-plan8-remedy` in `/Volumes/littlebig/refmatrix-t05-green`, at RED tip
`f3443130` (red-t05: `f81fe570`, `f3443130`). GREEN changes `src/` and docs only; no test was
edited. Test runs on the mini lane (`scripts/lane-mini.sh`), logs under
`workflow/review-output/t05-green-*.log`. {#lead}

## What was built {#built}

- **R5.3 (#s-4): `brief` is verb-first.** The `rmx_memory` verb gains `compile: bool = False`.
  `_memory_payload` forwards only the switch; the `memory_brief` daemon op builds the plan
  with the real `consolidate.compile_memories` at its default knobs on the request's compile
  scope, inside the same `_derive` read closure the briefs derive in, so plan and briefs read
  one snapshot. A compiling brief reads through `_read_with_fallback(..., private=True)`: the
  clustering pass takes seconds and would otherwise hold the shared mirror's reader lock
  (ch-bsd r9 #b-2's mechanism). The CLI `--compile` is a pass-through (`compile=True`); the
  CLI no longer calls `compile_memories` or `_read_store`, so `plan` stays None. MCP takes
  the parameter from the generated verb schema (`compile`: boolean, with a description);
  nothing was hand-written in `mcp.py`. {#built-r5-3}
- **The `plan` + `compile` refusal (lead ruling).** The verb raises `VerbArgsError` before any
  daemon call: `memory brief: \`plan\` and \`compile\` are exclusive; \`compile\` builds the
  plan in the daemon from the snapshot the briefs read, \`plan\` supplies one already built.
  Pass one, not both`. The op refuses the same pair for any other caller (`ValueError`,
  `memory_brief: \`plan\` and \`compile\` are exclusive; pass one, not both`). The CLI cannot
  send both. RED owns the test for it. {#built-refusal}
- **Budget.** A compiling brief pays the clustering pass inside the op, which the 10 s brief
  read budget was never sized for (before T0.5 the CLI ran that pass in its own process,
  unbounded). It gets `MEMORY_COMPILE_TIMEOUT_S`, one attempt, as `memory_compile` does; a
  compiling `--save` also goes once (`retries=0`). An explicit `timeout` still wins.
  {#built-budget}
- **R5.2 (#b-3, ruling O2).** `brief.parse_gmd`, `_parse_evidence` and the two regexes only
  they used (`_BRIEF_RE`, `_EV_ANY_RE`) are deleted. `ingest_gmd.parse_gmd` is untouched. A
  comment at the index section of `brief.py` says the index is one-directional and why;
  `render_gmd`'s evidence comment no longer claims a read-back. The dated note is in
  [[plan-8-derived-coverage-notes#one-directional]] and task 8.3's spec carries the superseded
  note (`status: complete` kept). {#built-r5-2}
- **R5.1, R5.5, AC-5.3, AC-5.4** are RED's tests; GREEN's part is the code above.
  `ENTRY_POINTS` (`compile_briefs`, `render_gmd`) still equals what `src/` calls from outside
  `brief.py`. {#built-tests}

## Files {#files}

- `src/refmatrix/brief.py`: the parse half deleted.
- `src/refmatrix/verbs.py`: `memory(..., compile: bool = False, ...)`; the refusal; the
  compile budget; `_memory_payload` forwards `compile`; `_MEMORY_DESCRIPTIONS` gains `compile`
  and `plan`.
- `src/refmatrix/daemon.py`: `_op_memory_brief` builds the plan when `compile` is set.
- `src/refmatrix/cli.py`: `memory brief --compile` passes through.
- `workflow/plans/plan-8-derived-coverage-notes.md`, task 8.3's spec: the notes.

`scripts/gen-cli-tree.py --check` (clone `src/` on `PYTHONPATH`): `ok: docs sections match
their render`; option help is not part of the rendered tree. {#files-docs}

## Verification {#verify}

The seven RED tests pass. Verify set (RED's set, every test that imports `refmatrix.mcp`,
calls the `rmx_memory` verb or touches the brief, and the five repo guards) at the GREEN tip:
see [[#verify-result]]. {#verify-lead}

Result at `fa3f887f` (mini lane, 46 files, `workflow/review-output/t05-green-verify-1.log`):
**1044 passed, 2 failed**. The two failures are bug-282 (open, mini lane only, same E line
`assert 0 == 2`): `test_mcp_session_pointer::test_owner_is_the_nearest_claude_ancestor_when_claude_pid_is_unset`
and `::test_owner_walk_reaches_claude_through_a_deep_chain`. The same file on the local lane at
the same sha: 62 passed (`workflow/review-output/t05-green-local-pointer.log`). The seven RED
tests pass, `test_brief_real_daemon`'s `[cli]` case included. An earlier run
(`t05-green-1.log`, `53ec47b0`) caught three `test_brief_surfaces` failures from passing
`private=` to `_read_with_fallback` on the non-compiling path, where the tests' doubles take
three positional arguments; `32c406e1` asks for `private` only when compiling. {#verify-result}

## Fold: bsd-t05 r1 (L188) {#fold-r1}

bsd-t05 r1 was DIRTY (1 BULLSHIT, 1 SKETCHY, 4 MEH). red-t05 wrote the REDs at `f97977b8`
(tests and registry only); GREEN's fold is `fa6d6f3e` plus this doc commit. {#fold-r1-lead}

- **#b-1: unembedded rows counted.** `compile_memories` clusters only rows with a vector, so
  an unembedded memory was in `stats.memories` and in no brief and no skip count, on every
  surface. `brief._plan_unembedded(plan)` counts them, and `compile_briefs` adds the count to
  `skipped` and `skipped_by["unembedded"]` whenever it has a plan. Both plan sources pass
  through `compile_briefs` (the op hands its compiled plan to it), so this is the one place
  and nothing is counted twice. The count is the plan's `stats["unembedded"]` capped by the
  rows the plan left unplaced (`candidates` minus cluster members minus `unclustered`). That
  handles `consolidate.compile_memories`' early return (fewer than 2 embedded rows put every
  row, unembedded ones included, in `unclustered`, so they become singletons, not skips), and
  a concept-only plan (every row "unembedded", every row placed) counts zero. The CLI's
  existing "N row(s) skipped (unembedded=3) — counted, not dropped" line reports it.
  {#fold-b-1}
- **#m-1.** `_op_memory_brief` is back to one call,
  `_read_with_fallback(d, part, _derive, private=compiling)`; RED graduated the
  `test_brief_surfaces` fakes to the `_daemon()` harness. {#fold-m-1}
- **#m-2.** The `classes_not_run` hint now reads "needs a `memory compile` plan; pass
  compile=true (CLI `--compile`) or a caller-built plan=". The singleton skip comment says
  snapshot skew applies only to a caller plan. {#fold-m-2}
- **#m-4.** Task 8.3's spec keeps its prose note and drops the non-standard
  `rel: superseded-by`; this summary carries `rel: supersedes` instead. {#fold-m-4}
- **L189 (bsd-t05 confirm-lite #b-1-r2).** The r1 count read the PLAN's corpus: after
  `brief --save`, the next compiling brief counted its 15 saved `brief/*` rows as unembedded
  (18 vs 3). Now `compile_briefs` counts over its OWN corpus rows (`brief._plan_unplaced`):
  a row whose name is in no cluster and not in `unclustered` is skipped, as `unembedded`
  when the plan embedded fewer rows than it considered, else `not_in_plan` (a row the plan
  never saw). `_plan_unembedded` is gone. `singleton` neither emits nor counts an
  `unclustered` name that exists in the store outside the brief's corpus; only a name the
  store lacks stays `singleton_unresolved`. The op's `compile_memories` call passes
  `exclude_mtypes=brief.EXCLUDE_MTYPES` (consolidate's defaults plus `brief`, `brief/*`), so
  the brief's own output never enters its plan; the corpus-side count still guards a caller
  plan. {#fold-l189}
- **#s-1, #m-3** were RED's (the G7 mirror probe; the dead-export guard's blind spots).
  {#fold-red}

Verify at the fold tip: see [[#fold-verify]].

Result at `468885f7` (mini lane, 90 files: RED's set, `test_read_path_partition_and_budget.py`,
every test that drives the `memory` CLI or the memory verb, and the five repo guards;
`workflow/review-output/t05-green-fold-verify.log`): **1793 passed, 2 failed**, both bug-282
(`test_mcp_session_pointer` owner walk, mini only, E `assert 0 == 2`). The six fold REDs pass
(`t05-green-fold-1.log`: brief detectors, real daemon, surfaces and read-path files, 59 passed).
{#fold-verify}

## Release {#release}

The MCP tool `rmx_memory` changes (a new `compile` parameter), so the release needs a deploy
and a `/mcp` reconnect in every client before an MCP caller sees it (AC-5.5). No version bump
in this branch. {#release-line}
