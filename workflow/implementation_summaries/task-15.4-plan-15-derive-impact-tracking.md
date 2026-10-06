---
gmd: "0.1"
id: task-15.4-summary
title: "Task 15.4 summary: the two passes that never stamped now do, and what is missing has a name"
tags: [implementation-summary, plan-15, derive]
metadata:
  node_type: summary
  task: task-15.4-stamp-coverage
  created: 2026-10-06
---

# Task 15.4 summary {#root}

rel: realizes -> [[task-15.4-stamp-coverage]]
rel: part-of -> [[plan-15-derive-impact-tracking]]
rel: depends-on -> [[task-15.1-per-pass-code-identity]]

## What was wrong {#problem}

`rmx reingest` runs five passes. Three stamped (`ingest`, `semantic`, `gmd`);
`sessions`, `embed` and `pagerank` recorded nothing. This project's own
`refmatrix` partition therefore carried exactly ONE derive row (`gmd`), so
`rmx derive status` answered for a graph four passes had touched, and the four
read as fresh because nothing named them. bug-039 one level down: a surface
complete enough to read as complete. {#problem-body}

## The three passes now stamp, at the END {#stamping}

- **pagerank** — `daemon._op_pagerank`, inside the same `_store_lock` that
  writes the scores and AFTER `store_scores`. The power iteration runs outside
  the lock and can raise; a stamp placed earlier would claim a derive that
  never landed. One site covers both routes, because the no-daemon CLI path
  calls `_op_pagerank` directly.
- **embed** — `cli.embed_cmd`, per partition, and ONLY when the batch loop ran
  to completion. A `--max-batches` run leaves rows pending, so stamping it
  would record a complete pass over a partition that is not finished; a new
  `completed` flag distinguishes the two exits.
- **sessions** — `cli.session_ingest_cmd`, on both index routes (daemon and
  in-proc) and on the all-cards-unchanged path, because a derive that changed
  nothing is still a derive (task 15.2) and the next run skips the same cards
  again. `--no-index` stamps NOTHING: cards on disk, store untouched.

`embed` and `sessions` complete in the CLI, which cannot open the active slot
while the daemon holds the writer, so both route through a new daemon op,
`derive_stamp` (`_op_derive_stamp`), via `cli._stamp_derive_pass` —
daemon-first, in-proc fallback, the same shape as `_run_pagerank`. A stamp
failure is PRINTED and the pass still counts as done: losing the record is bad,
losing the derive to protect the record would be worse, and silence is the one
option a memory path does not have. {#stamp-route}

All three got `_DERIVE_PASS_MODULES` entries (`sessions` →
`session_ingest.py` + `ingest_gmd.py`, `embed` → `embedder.py` + `vectors.py`,
`pagerank` → `pagerank.py`). Without them each new pass falls through to the
union of three modules and an edit to `ingest.py` would read as pagerank
staleness — exactly the attribution task 15.1 removed. {#modules}

## What is missing now has a name, per partition KIND {#coverage}

`store._DERIVE_EXPECTED_PASSES` declares the expected set for each of three
kinds, and `partition_kind` / `derive_expected_passes` classify a partition:
`sessions-*` → sessions, `memory-*` or `global` → memory, else project, with
one root-based exception — a memory-ONLY root (`is_memory_only_root`) answers
`memory` whatever its partition is called, so the global store is never
reported as missing `ingest`, a pass it is structurally forbidden to run.
{#kinds}

`derive_status()` gained `partition_kind`, `expected_passes` and
`missing_passes`. An EMPTY partition (no stamp, no tracked file) reports no
missing passes: there is nothing to derive, and five lines on every fresh store
is how a coverage report gets ignored. {#status-fields}

Rendered in two places: `rmx derive status` prints one line per missing pass
AFTER the stamped rows (a reader who sees three green lines and no fourth has
no way to know a fourth was expected), and `rmx reingest` prints a coverage
line per partition it touched. {#render}

## Missing is NOT an alert {#not-an-alert}

`missing_passes` sets neither `stale` nor `behind_code` nor `never_stamped`, so
it never reaches `hub`'s hot gate — which fires on `derive["stale"]` alone. On
the release that ships this, every store in the fleet is missing four of five
stamps, and a gate that fired on that would alert all eight rows once and be
switched off forever (ch-bsd plan-12 #b-3, measured). The test asserts
`_store_health`'s dict directly, because that is the blast radius, not a dict
the test built. {#not-an-alert-body}

## A skipped pass is distinguishable from an absent one {#skipped}

`--no-semantic` / `--no-sessions` / `--no-embed` are the operator's choice, and
the run knows it, so `render_derive_coverage(..., skipped=(...))` labels them
`skipped this run` instead of listing them as never stamped. No schema change:
the skip is a property of the RUN, not of the store, and persisting it would
make a store claim knowledge about a pass nobody ran. {#skipped-body}

## Found by running the real command {#the-rendering-bug}

The first live `rmx reingest` printed `derive coverage:` with the partition name
GONE — rich read `[proj]` as a style tag and dropped it. A coverage report that
cannot say WHICH partition is uncovered is the blind spot again, one layer out.
Fixed with the `rich_escape` the warning renderer beside it already used, and
pinned by a test asserting the project name appears in the real CLI output.
Same defect family as the renderer that ate `[[wikilinks]]` (ch-bsd plans 7-10
r3). {#rendering-body}

rel: reinforces -> [[feedback_green_tests_are_not_a_working_command]]

## Tests {#tests}

`tests/test_derive_coverage.py`, 22 tests, 17 RED before the fix
(`workflow/review-output/pytest-task154-RED.log`). The three that passed at RED
were the raise-cases, vacuous until pagerank stamped at all — named here rather
than left to look like coverage, per
`feedback_clean_corpus_hides_a_dead_gate`. Criterion 2 patches the EXTRACTOR
(`pagerank.pagerank`), never `stamp_derive`; criterion 6 runs the real CLI with
the flag; the sessions and embed tests drive the real commands, with only the
model-bearing `_op_embed` faked. {#tests-body}
