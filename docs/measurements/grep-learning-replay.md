---
gmd: "0.1"
id: refmatrix/grep-learning-replay
title: "What the grep→graph learning loop actually buys: a two-arm replay of this project's own grep history"
tags: [measurement, grep, learning, telemetry, plan-14]
metadata:
  node_type: measurement
  created: 2026-10-06
  harness: eval/production/grep_learning_replay.py
  results: eval/production/results/grep_learning/
---

# Does funnelling grep through rmx teach the graph anything? {#root}

rel: realizes -> [[task-14.4-replay-measurement]]
rel: part-of -> [[plan-14-grep-learning-measurement]]
rel: derives-from -> [[project_grep_learn_wall_and_queue]]
rel: evidence-for -> [[bug_registry]]
rel: reinforces -> [[feedback_causal_story_before_evidence]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]

**Answer: yes, and by a margin that clears the pre-registered threshold six times over — but only
after a defect found BY this instrument was fixed. Before that fix the loop was teaching concepts
its own lookup could not retrieve.** {#answer}

Every bare `grep` on this machine is rewritten to `rmx grep`, and every `rmx grep` that falls to the
tool floor teaches the graph a `query/PATTERN` concept. The loop's COST has been measured since the
30 s wall ([[project_grep_learn_wall_and_queue]]). Its BENEFIT had never been measured at all,
because nothing in `query.log` said whether the index or the floor answered a call. Task 14.1 added
that field; this is what it says. {#why}

## The headline {#primary}

Two stores built from ONE corpus snapshot (`src` + `docs`, 111 entities) through the production
ingest path, then this project's real grep history replayed against both in timestamp order — 1,557
calls from `.refmatrix/query.log`. The arms differ in exactly one bit, the learning toggle, and the
report does not take the harness's word for it: every row carries its own effective `learn` state,
and the two arms read `{"True": 1557}` and `{"False": 1557}`. {#setup}

| | arm A (learning ON) | arm B (learning OFF) |
|---|---|---|
| answered from the **index** | **493 (31.7%)** | 288 (18.5%) |
| answered from the tool **floor** | 1,064 | 1,269 |
| learned `query/*` concepts | 1,733 | **0** |
| teaches applied by the drain | 7,637 | 0 (`skipped: learning-disabled`) |

**+205 calls moved from the floor to the index — +13.2 points.** Arm B's 18.5% is the ingest-only
baseline: what the graph answers from having read the corpus. The difference is what the read-path
teach adds on top. {#delta}

## The pre-registered threshold {#threshold}

Stated in [[plan-14-grep-learning-measurement#negative-criterion]] before any number existed, so it
could not move afterwards: a negative result if the learned index answers **under 5% of eligible
exploration calls**, or answers them with rows no better than the floor's. {#criterion}

**Not met, on both halves.** 31.7% against a 5% floor, and the rows are the floor's own answers
(precision median 1.000, below). The loop pays for itself on this workload. {#verdict}

## Quality: when the index answers, is it right? {#quality}

The index/floor ratio cannot see a loop that answers *wrongly* from the index, so each learned
answer is scored against a control. **The control is the producer the floor itself used** —
`rg -nH --no-heading`, the exact call `_grep_rg_fallback` makes. Two metrics, and the distinction is
load-bearing: {#control}

- **precision** — of the rows the index returned, how many name a `file:line` where the pattern
  really matches. This is the number that can indict the loop.
- **coverage** — of the lines the control finds, how many the index returned. **Not a quality
  bound**: the index answers with the top `--limit` references by design, so coverage on a common
  token is low for the same reason `head -5` "loses" lines.

Over 59 patterns answered from learned rows: {#quality-numbers}

| | value |
|---|---|
| precision, median | **1.000** |
| precision, mean | 0.901 |
| precision = 1.0 | 48 / 59 |
| precision ≥ 0.9 | 50 / 59 |
| precision < 0.5 | 4 / 59 |
| coverage, median | 1.000 |

A median of 1.000 on both means that for most patterns the index returns **exactly** the line set
real grep would have, with no startup cost and no tree walk.

### The four that are not clean, and whose fault each is {#precision-outliers}

`ERROR`, `error:`, `' error: '` and `timeout` score 0.00-0.50, and the cause splits in two — measured
by running the lookup with and without the canonical predicate on the same store, not inferred:
{#outlier-split}

| pattern | rows, name-match only | rows, with canonical | whose |
|---|---|---|---|
| `ERROR` | 62 | 62 | pre-existing: substring `ILIKE` over concept names |
| `error:` | 0 | 62 | **the bug-067 fix**: canonicalization drops the `:` and the pattern joins the whole `error` family |
| `roaring bitmap` | 0 | 10 | the fix working as intended |

So a short token that differs from a learned concept only by punctuation now matches that concept's
whole family. The breadth itself is older than the fix (`ERROR` returns 62 rows either way), but the
fix extends it to punctuated spellings. Logged as bug-070 rather than retuned here: changing it
trades the ingest-side gain below against this precision cost, and that is a decision to take with a
measurement in hand, not at the end of the session that produced it. {#outlier-verdict}

## The defect this instrument found first {#bug-067}

The first replay said the loop moved almost nothing. That was not a verdict on the loop — it was
bug-067. `add_concept` writes the canonical underscore row PLUS space and dash ALIAS rows as
separate entities, `_learn_grep_hits` attaches every piece of evidence to the canonical id, and the
read matched `c.name ILIKE '%literal%'` then JOINed evidence. Proven by direct SQL: {#mechanism}

```
query/roaring bitmap   evidence=0     <- the literal the next grep looks for
query/roaring-bitmap   evidence=0
query/roaring_bitmap   evidence=10    <- where the evidence actually went
```

So `rmx grep`'s promise that "future searches hit the index" held only for patterns whose literal
form already was their canonical one. The fix is the read consulting `canonical_name`, the same
resolution `resolve_concept_ids` has always used for query/context/neighbors. Measured on the
reachability harness (teach → drain → re-query, per pattern, the most generous timing the loop can
ever be given), over the 122 patterns that repeat in the real log: {#fix}

| | before the fix | after |
|---|---|---|
| taught, then reachable on the immediate repeat | 24/76 (31.6%) | **50/61 (82.0%)** |
| multi-word patterns | **0/18** | 14/15 |
| answered from the index on the FIRST call | 29/121 | **43/122** |

The third row is a side effect worth naming: the canonical predicate also reaches INGEST-time
concepts, so 14 more patterns are answered from the index before any learning happens. 11 patterns
remain unreachable, 10 of them regexes whose learned name is the literal regex text — a limitation
recorded in the row, not the same defect. {#fix-numbers}

## What it costs {#cost}

Measured in this run rather than cited from the old one
([[feedback_measure_the_outcome_not_the_wall]]): {#cost-lead}

| | arm A | arm B |
|---|---|---|
| catalog size | 62.7 MB | 17.6 MB |
| drain time (CPU, 7,637 teaches) | 512 s | 0 s |
| replay wall | 879.7 s | 337.2 s |
| grep latency p50 | 23 ms | 19 ms |

**3.6x the catalog and 512 s of writer time for 1,557 greps.** The wall-clock gap is almost entirely
the drain, which in production is the daemon's background tick rather than the read path — the CLI
pays `LEARN_BROKER_TIMEOUT_S` to append to a queue and nothing more. The p50 read latency is 4 ms
apart, so this is a storage and background-write cost, not a read cost. Whether 45 MB per project is
worth 13 points of index share is a product decision; the numbers are now on the table for it.
{#cost-verdict}

## What this does NOT say {#limits}

Stated so no later reader over-reads it: {#limits-lead}

- **Not the eligible share of live traffic.** `_index_may_answer` is `return not paths`, so the index
  only ever answers exploration (`rmx grep PATTERN`); a drop-in read that names files is answered by
  the tool by contract. Historical rows hold the pattern and not the paths, so what fraction of real
  greps the index was even allowed to answer is unrecoverable, and only forward `answered_by` data
  can supply it. The replay issues exploration calls, and `dropin`/`stdin` are 0 by construction.
- **Not the daemon's tick.** The harness calls the real `_drain_learn_queue` directly rather than
  running a daemon per arm, because throwaway daemons would register throwaway stores with the
  machine's hub. The drain is in scope; its scheduler is not.
- **Not the original flags.** `query.log` records the pattern and not the flags, so a BRE-invalid
  pattern is retried once as ERE — an approximation, named in the harness.
- **Not a latency claim.** Greps are real subprocesses, so startup is included; the p50s above are
  context, not a benchmark.

## Reproducing it {#repro}

```bash
# the headline (two arms, ~20 min)
.venv-eval/bin/python eval/production/grep_learning_replay.py --corpus src docs \
  --out workflow/review-output/grep-replay-full.json

# reachability + quality (~3 min)
.venv-eval/bin/python eval/production/grep_learning_replay.py --reachability \
  --repeated-only --corpus src docs \
  --out workflow/review-output/grep-reachability-quality.json
```

Both arms run under a short `mkdtemp()` root (macOS caps a unix socket path at ~104 bytes) with
`RMX_CLAUDE_HOOKS_DIR` redirected, so no run can touch the live store or `~/.claude/hooks`. Raw
JSON for every number above is committed under `eval/production/results/grep_learning/`. {#repro-note}
