---
gmd: "0.1"
id: task-15.4-stamp-coverage
title: "Task 15.4: the passes that never stamp are named, not assumed fresh"
tags: [task, derive, coverage]
metadata:
  node_type: task
  status: completed
  created: 2026-10-06
---

# Task 15.4: coverage {#root}

> Plan: [plan-15-derive-impact-tracking](../plan-15-derive-impact-tracking.md)
> Status: Completed (2026-10-06)
> Depends on: Task 15.1

rel: part-of -> [[plan-15-derive-impact-tracking]]
rel: depends-on -> [[task-15.1-per-pass-code-identity]]

## Requirements {#requirements}

`rmx reingest` runs five passes. Three stamp (`ingest`, `semantic`, `gmd`); **sessions, embed and
pagerank never do**, and this project's own `refmatrix` partition currently carries exactly ONE row
(`gmd`). So "the derived graph was built by 0.73.0" is a claim about one pass out of five, and the
other four are invisible rather than fresh. {#req-lead}

Two halves, and the second is the one that cannot be skipped: {#req-halves}

1. **Stamp the rest.** `sessions`, `embed` and `pagerank` call `stamp_derive` at the end of a
   successful pass, the same way `_stamp_ingest` does — at the END, so a crashed pass leaves the
   previous stamp standing rather than claiming a derive that did not finish.
2. **Name what is missing.** `derive_status()` reports the set of passes it EXPECTS and which of
   them have no stamp, so a partition with one row out of five says so instead of answering for the
   graph. The expected set is a named constant beside the module mapping, not a literal in a
   reporter — a list in the renderer is how coverage drifts without anyone noticing.

The expected-pass set is per PARTITION KIND, because a memory partition has no sessions pass and a
sessions partition has no gmd pass. A partition must not be reported as missing a pass it can never
run; that is a false positive with the same cost as the one 15.1 removes. {#req-kinds}

An unstamped pass is NOT `behind_code`. On the release that introduces stamping, every store is
unstamped, and a gate that fired on that would alert every row once and then be switched off —
ch-bsd plan-12 #b-3 measured exactly that failure. Unstamped is its own state (`never_stamped`
already exists for the whole partition; this extends it per pass). {#req-not-alert}

## Acceptance criteria {#acceptance}

1. A full `rmx reingest` on a fresh store leaves a stamp AND a history row for every pass that ran.
2. A pass that RAISES leaves no stamp for itself and does not prevent the others from stamping.
3. `derive_status()` on a partition with one stamp out of five lists the four missing by name.
4. A sessions partition is not reported as missing `gmd`, and a memory partition is not reported as
   missing `sessions` — asserted per partition kind.
5. An unstamped pass does not set `behind_code` and does not reach the hub alert. Pinned by a test,
   because this is the half that would turn the whole fleet hot on the release that ships it.
6. `--no-semantic`, `--no-sessions` and `--no-embed` do not produce a "missing" report for the pass
   the operator deliberately skipped: a skipped pass is distinguishable from an absent one.

## Files to modify {#files-to-modify}

| File | Change |
|------|--------|
| `src/refmatrix/ingest.py` | sessions pass stamps |
| `src/refmatrix/store.py` | `_DERIVE_EXPECTED_PASSES` per partition kind; `derive_status` reports missing; embed + pagerank stamp where they complete |
| `src/refmatrix/cli.py` or `daemon.py` | wherever embed and pagerank complete, whichever owns the end of those passes |

## Test strategy {#test-strategy}

`tests/test_derive_coverage.py`. Criterion 2 drives a real raising pass (monkeypatch the EXTRACTOR
it calls, not `stamp_derive` — patching the stamp would test the test). Criterion 5 asserts the hub
alert input directly, since that is the blast radius. Criterion 6 runs the real CLI with the flag.
{#tests}
