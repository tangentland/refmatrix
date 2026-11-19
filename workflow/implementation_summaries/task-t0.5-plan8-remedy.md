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

Result: pending the lane run. {#verify-result}

## Release {#release}

The MCP tool `rmx_memory` changes (a new `compile` parameter), so the release needs a deploy
and a `/mcp` reconnect in every client before an MCP caller sees it (AC-5.5). No version bump
in this branch. {#release-line}
