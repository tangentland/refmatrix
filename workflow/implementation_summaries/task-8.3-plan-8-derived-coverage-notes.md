---
gmd: "0.1"
id: task-8.3-summary
title: "Task 8.3 summary: the brief GMD index and its round trip (written retroactively)"
tags: [implementation-summary, plan-8]
metadata:
  node_type: summary
  task: task-8.3-plan-8-derived-coverage-notes
  created: 2026-10-19
  retroactive: true
---

# Task 8.3 summary {#root}

rel: realizes -> [[task-8.3-plan-8-derived-coverage-notes]]
rel: part-of -> [[plan-8-derived-coverage-notes]]
rel: amends -> [[task-8.2-summary]]
rel: derives-from -> [[bsd-plan7-10-r1-399d0a3]]
rel: derives-from -> [[bsd-plan7-10-r3-4f451c5]]
rel: derives-from -> [[bsd-plan7-10-r4-05bef34]]
rel: derives-from -> [[bsd-plan8-9-10-r5-e0b7df6]]
rel: depends-on -> [[plan-review-2026-10-14#t11-folded-waves]]

Written retroactively on 2026-10-19 in the W1-d bookkeeping sweep. The task spec's `#done` names
this file by exact path, and r5 `#s-6-r5` flagged it as absent. The build was first written up,
together with task 8.2, in [[task-8.2-summary#index]] (committed in `71ee227`). This file adds the
commit trail, the four ch-bsd rounds that found `--gmd` broken in a different way each time, and
what is still open.

## What shipped {#shipped}

- **`7cc26d8`** (2026-09-15), `feat(memory): rmx memory brief — verb, daemon op, CLI, MCP, GMD
  index`. This one commit covers tasks 8.2 and 8.3. For 8.3 it adds `brief.render_gmd` /
  `brief.parse_gmd` in `src/refmatrix/brief.py` and `tests/test_brief_gmd.py` (186 lines). It is
  reachable from `origin/master`.
- `render_gmd` sorts by `(class, label)` so that the output is byte-stable. It emits
  `rel: evidence-for` edges to each cited memory. An unresolvable evidence id is shown but not
  emitted as an edge, and the evidence count never shrinks.

## Four rounds, four different ways `--gmd` was wrong {#rounds}

| Round | Finding | Fix commit | What was wrong |
|---|---|---|---|
| r1 | `#b-1` | `0b5adc9` | `--gmd` raised `AttributeError` on every real invocation: the wire carries dicts, and `render_gmd` read attributes |
| r1 | `#b-5` | `0b5adc9` | the round-trip test smuggled `evidence=[1, 2]` back in, and `parse_gmd` recovered no evidence. The render now carries each id beside its link, and `parse_gmd` reads both forms |
| r3 | `#b-1-r3` | `6b6a610` | `console.print` parsed `[[name]]` as rich markup, so every edge shipped as `rel: evidence-for -> []`. `tools/gmd/lint.py` reported 0 errors on that output. Fixed with `click.echo` |
| r4 | `#b-1-r4` | `8c090f0` | `render_gmd(stats=)` had no production caller, so every real document said "an unrecorded number of memories" |

r5 reproduced the r4 closure on the live store with the deployed binary: `9 brief(s) over 274
memories`, with the `--json` output and the table agreeing ([[bsd-plan8-9-10-r5-e0b7df6#closed]]).
r5 also recovered 9 of 9 briefs, with evidence ids, by running `parse_gmd` over that document.

## Definition-of-done record {#done-record}

- RED / GREEN: [[task-8.2-summary#tests]] names `red-task-8.3.log` and `green-task-8.3.log` under
  `workflow/review-output/`. That directory is gitignored, so this sweep could not verify the
  logs.
- Spec test "round trip: render -> `ingest-gmd --as-memory` into a fresh store -> re-render is
  byte-identical": **not built as specified**. `tests/test_brief_gmd.py` has no `ingest_gmd` call.
  Its round trip is `render -> parse_gmd -> render` in-process
  (`test_render_parse_render_is_byte_identical`).
- Spec mutation "dropping one brief's `rel:` edges turns the resolve test RED": not recorded. The
  8.2/8.3 commit reports "Nine mutants killed" across both tasks and does not attribute them.
- Branch: no `task-8.3-plan-8-derived-coverage-notes` branch exists in this clone. Not recorded
  whether one ever existed.

## Still open {#open}

All of the following are r5 findings ([[bsd-plan8-9-10-r5-e0b7df6]]), owned by **W2-b**
([[plan-review-2026-10-14#t11-folded-waves]]):

- **`#b-3-r5`**: `brief.parse_gmd`, the "store is rebuildable from the index" direction this task
  exists for, has no production caller. No CLI command, verb action or daemon op reads an index
  back. Its `names=` / `ids_by_name` parameter is dead. `--gmd` writes only to stdout (there is no
  `--out`). The fix is to expose it, or to delete it and amend plan-8 `#proposed-approach` to claim
  one direction only.
- **`#b-2-r5`**: the `corroborated` call site can be deleted with the suite still green (plan-8's
  own `#execution` gate).
- **`#s-4-r5`**: `--compile` is implemented in the CLI, not in the verb. MCP callers can therefore
  reach only 2 of the 4 shipped detectors.
- **`#s-9-r5` / `#m-10-r5`**: four unregistered doubles in `tests/test_plan7_10_remedy_r4.py`. The
  brief parity gate counts the population of parameters, not the set it actually compares.

Plan-8 deferrals, owned by **W3-b**: the `brief/stale` detector (`deferral_registry.md` row 44) and
the answer-usefulness miss signal.
