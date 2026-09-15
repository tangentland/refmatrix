---
gmd: "0.1"
id: task-8.3-plan-8-derived-coverage-notes
title: "Task 8.3: GMD index render and regenerate-from-store round trip"
tags: [task, plan-8]
metadata:
  node_type: task
  status: pending
  plan: plan-8-derived-coverage-notes
---

# Task 8.3: GMD index render and regenerate-from-store round trip {#root}

> Plan: [[plan-8-derived-coverage-notes]]
> Status: Pending
> Depends on: 8.1

rel: part-of -> [[plan-8-derived-coverage-notes]]

## Requirements {#requirements}

- `rmx memory brief --gmd` renders a `memory-briefs` GMD doc: frontmatter, `{#anchor}` on every heading, `rel:` edges from each brief to the memories it cites. Zero `tools/gmd/lint.py` errors.
- Honors the same both-directions contract `memory compile` states: the index is regenerable from the store, and the store is rebuildable from the index (`ingest-gmd --as-memory`).
- The doc says plainly that it is derived and names the command that regenerates it — `consolidate.render_gmd` already carries that line; match it.

## Files to Create / Modify {#files}

- modify `src/refmatrix/brief.py` (render + parse)

## Test Strategy (RED first) {#test-strategy}

`tests/test_brief_gmd.py`:
- rendered output passes `tools/gmd/lint.py` with zero errors
- every `rel:` target in the render resolves to a memory id present in the store
- round trip: render -> `ingest-gmd --as-memory` into a fresh store -> re-render is byte-identical
- mutation check: dropping one brief's `rel:` edges turns the resolve test RED

## Definition of done {#done}

- RED run recorded, GREEN run recorded, mutation check noted in the implementation summary.
- Implementation summary at `workflow/implementation_summaries/task-8.3-plan-8-derived-coverage-notes.md`.
- Committed on branch `task-8.3-plan-8-derived-coverage-notes`; merged `--no-ff` to `master`.
