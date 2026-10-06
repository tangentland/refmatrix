---
gmd: "0.1"
id: task-15.3-derive-surface
title: "Task 15.3: rmx derive log / diff, and a status line that says which pass and why"
tags: [task, derive, cli, verbs]
metadata:
  node_type: task
  status: complete
  created: 2026-10-06
---

# Task 15.3: the surface {#root}

> Plan: [plan-15-derive-impact-tracking](../plan-15-derive-impact-tracking.md)
> Status: Complete
> Depends on: Task 15.1, Task 15.2

rel: part-of -> [[plan-15-derive-impact-tracking]]
rel: depends-on -> [[task-15.2-derive-history-and-counts]]

## Requirements {#requirements}

**`rmx derive log`** — the history for this store: one line per derive, newest first, with pass,
version, code hash (short), age, duration, and the delta against the previous row for that pass.
`--pass NAME` filters, `--limit N` caps, `--json` for machines. A pass with one row shows its counts
and says there is nothing to compare to — not a delta against zero. {#req-log}

**`rmx derive diff [A] [B]`** — the counts delta between two derives of one pass, defaulting to the
two most recent. Prints only keys that moved, plus an explicit "no change" when nothing did, because
a silent empty table reads as a broken command. {#req-diff}

**`rmx derive status`** — what `rmx daemon status` says today, but per pass and attributed: which
pass, whether it is behind by CODE or only by VERSION, and which modules that pass's hash covers.
The current line (`derive[refmatrix]: 0.73.0 (running 0.74.1) — stale`) leads with the version
comparison, which fires on every bump and is the reason this reads as noise. {#req-status}

The daemon status line and `rmx fingerprint`'s `reasons` are updated to name the PASS and the axis
(code vs version). `fingerprint`'s `trustworthy` gate keeps its current meaning — it already reads
`derive_stale`, and this task must not make an eval newly untrustworthy for a version bump that
touched no extractor. {#req-callers}

Reads only. Nothing in this task writes to a store; `derive log`/`diff`/`status` route through the
daemon read path like every other read surface. {#req-readonly}

## Acceptance criteria {#acceptance}

1. `rmx derive log` on a store with history prints one line per derive with a delta column; with no
   history it says so and exits 0.
2. `rmx derive diff` on two identical derives prints "no change" explicitly.
3. `rmx derive diff` on a real change prints the moved keys and omits the unmoved ones.
4. `rmx derive status` names the pass and distinguishes code-stale from version-stale. On THIS store
   it reports `gmd` as version-stale and NOT code-stale (plan acceptance #1).
5. `--json` output is parseable and carries the same numbers as the table.
6. Verb parity: if any of these is exposed over MCP it is a verb first; if not exposed, the parity
   test still passes. (`rmx learn` set the precedent for an operator surface with no MCP tool.)
7. `rmx fingerprint` does not newly fail `trustworthy` on a version-only bump.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/cli.py` | the `derive` command group |
| `src/refmatrix/daemon.py` | the status line names pass + axis; a read op for history if the CLI needs one |
| `src/refmatrix/store.py` | `derive_status` already carries per-pass detail from 15.1; add the diff helper if it belongs with the data |

## Test strategy {#test-strategy}

`tests/test_derive_surface.py` via `CliRunner` against real stores with real history rows written by
real derives. The "no change" case asserts the WORDS, because an empty table and a no-change result
are indistinguishable to a caller otherwise — which is the bug-058 shape (a short read that looks
successful). One case per criterion, RED first. {#tests}
