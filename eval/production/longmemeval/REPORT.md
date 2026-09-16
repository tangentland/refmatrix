---
gmd: "0.1"
id: longmemeval-report
title: "LongMemEval on the production path — symbolic surfaces, 120 stratified questions"
tags: [eval, benchmark, longmemeval, plan-7]
metadata:
  node_type: report
  created: 2026-09-15
  rmx_version: "0.69.1"
---

# LongMemEval, production path {#root}

rel: realizes -> [[task-7.4-plan-7-longmemeval]]
rel: part-of -> [[plan-7-longmemeval]]
rel: evidence-for -> [[longmemeval-latency]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]

**Every number here is depth-bound and must be read with its ceiling. See [[#saturation]] before
quoting anything.**

## Setup {#setup}

| | |
|---|---|
| dataset | `longmemeval_s` (HuggingFace `xiaowu0162/longmemeval`) |
| corpus | 19,829 unique session docs (25,112 haystack slots, deduped, 0 content conflicts) |
| graph | 406,885 concepts, 2.53 GB catalog |
| build | `rmx init` → `ingest-gmd --as-memory` → (embed FAILED, see [[#embed]]) |
| ingest time | **15,775 s (4h23m)** |
| questions scored | **120** — type-stratified, 20 per type, seed 42 |
| retrieval depth | **50 for `context`; `scan` is DEPTH-UNCONTROLLED** (see [[#saturation]]) |
| binary | deploy `rmx` 0.69.1, daemon up and warm |
| date | 2026-09-15 |

## Results — `restricted` mode {#restricted}

`restricted` = retrieve deep through the CLI, filter the ranked list to the question's own
~50-session haystack, cut to k. Comparable in SHAPE to published figures; see [[#not-comparable]].

| surface | MRR@20 | R@1 | R@5 | hit@5 | **ceiling** |
|---|---:|---:|---:|---:|---:|
| `context` | 0.679 | 0.476 | 0.605 | 0.683 | **0.683** |
| `scan` * | 0.637 | 0.445 | 0.547 | 0.642 | **0.642** |

\* `scan` is DEPTH-UNCONTROLLED — its ceiling is scan-prompt's default pool, NOT a depth-50 pool.
Do not read it against `context`'s row as though one knob produced both.

## THE RESULT IS SATURATED — read this before the table {#saturation}

`context` scores **hit@5 = 0.683 against a ceiling of 0.683**. `scan` scores 0.642 against 0.642.

The ceiling is the fraction of questions whose gold session appeared ANYWHERE in the retrieved
pool. Hitting it exactly means **every gold session that entered the pool was ranked into the top
5**. So neither number measures ranking quality. They measure how often retrieval reached the gold
session at all.

**The two rows are bounded by DIFFERENT things and are not comparable to each other:**

- `context` — pool = `--max-entities 50`. **R@5 = 0.605 is a floor set by retrieval depth.**
  Raising `--depth` raises both its ceiling and its score with no change to the ranker.
- `scan` — **DEPTH-UNCONTROLLED.** `--depth` never reached it: `--max-tokens` is inert in JSON
  mode and `scan.py` cuts at `matches[:max_concepts]` before budgeting (measured, ch-bsd r2
  #b-6-r2). Its 0.642 is scan-prompt's DEFAULT pool, and `--depth 200` will not move it.

## Per question type {#per-type}

| type | `context` R@5 | `scan` R@5 |
|---|---:|---:|
| single-session-assistant | 0.950 | 0.950 |
| knowledge-update | 0.925 | 0.800 |
| multi-session | 0.567 | 0.454 |
| single-session-user | 0.500 | 0.450 |
| temporal-reasoning | 0.487 | 0.477 |
| **single-session-preference** | **0.200** | **0.150** |

Two readings, both uncomfortable:

**Preference retrieval nearly fails.** 0.200 — six times worse than knowledge-update on the same
corpus and surface. A preference is stated once, casually, in vocabulary that never recurs; the
`mentions` index has nothing to grip.

**Multi-session and temporal-reasoning are MID-TABLE, below the single-session types.** Those are
precisely the two types the conceptual-memory thesis predicts the graph should win. On this
evidence it does not. The honest qualifier: this corpus has **no structural edges at all** — no
calls, defines, or imports — so the half of the graph that wins CSN is absent by construction, and
rmx is reduced to its associative layer. That is an explanation, not a defence: a memory product
meets prose corpora in the field.

## `union` vs `restricted` {#union}

`scan` union R@5 **0.465** vs restricted **0.547**. The gap is small only because both are
depth-bound. `context` union did not complete in this batch.

## Latency — RETRACTED, see the profile {#latency}

An earlier version of this report claimed `rmx context` costs **62.9 s** per query here and that
rmx is ~4,500x slower than agentmemory's published 14 ms. **That is retracted.** The number was
measured while the daemon was building a 432 MB adjacency cache and replicating three 2.4 GB
catalog slots — a storm window reported as steady state.

Profiled 2026-09-16: `build_context` warm is **0.45 s**, of which BM25 over 406,885 concepts plus
the graph walk is **0.37 s**. The retrieval core is not slow. What remains unexplained is an ~8.5 s
gap between `build_context` (0.45 s) and the full daemonless CLI (9.0 s), of which only 2.8 s is
CPU. That gap is not yet attributed.

**No per-query latency figure for this corpus should be quoted** until the store is re-measured
quiet. Full retraction and decomposition: `workflow/measurements/longmemeval-latency.md`.

## NOT comparable to published figures {#not-comparable}

External landmarks, quoted as landmarks and nothing more — different harness, embedding model,
chunking, and haystack scoping:

| system | claimed |
|---|---|
| agentmemory | 95.2% R@5 on LongMemEval-S, 500 questions |
| mcp-memory-service | 80.4% R@5, 89.1% MRR; multi-session 70.7%, temporal-reasoning 72.0% |

**Do not put 0.605 beside 95.2%.** Three reasons, each sufficient: this run is depth-50 SATURATED;
`restricted` is a post-hoc filter, not a per-question index (no CLI exposes
`ann_search(candidate_ids=...)`); and neither published figure states its haystack scoping.

## The dense half is missing {#embed}

`rmx embed --kinds memory` failed after 30.8 s on a model-worker socket `TimeoutError`, aborting
the build before `memory compile`. Cause: `WorkerClient.call(timeout=X)` mutates the PERSISTENT
socket timeout and never restores it, so a bounded probe leaks its budget onto the next call —
**bug-030**, second sighting of `impression_bsd_probe_timeout_leak`.

So `recall`, `recall-fuse`, `recall-rr`, `recall-fuse-rr` have no numbers here. The ingest is
persisted, so embed resumes via `ingest.py --skip init --skip ingest-gmd` without repeating the
4h23m.

## Reproduce {#reproduce}

```bash
cd eval/production/longmemeval
python3 prepare.py --fetch --split s --per-type 20
python3 ingest.py
REFMATRIX_ROOT=<data>/.refmatrix python3 run.py \
    --method context --method scan --subset 20 --depth 50 --at 1,5,10,20 --workers 4
```

`--depth 50` applies to `context` only; `scan` ignores it and records `depth: null`.

Committed results: `eval/production/longmemeval/results/summary-symbolic-120.json`.

## Next, in priority order {#next}

1. **Re-run at `--depth 200`.** Until the ceiling is unsaturated these are not ranking numbers.
   Runtime unknown — the "~4 h" an earlier version of this list gave was derived from the retracted
   62.9 s figure and is withdrawn with it. **`--depth` reaches only `context`.** b-6 was NOT
   fixed: two attempted fixes were both inert and a third guess was declined (ch-bsd r1 #b-6,
   r2 #b-6-r2), so `scan` is permanently DEPTH-UNCONTROLLED, its committed 0.642 is scan-prompt's
   DEFAULT pool, and re-running at 200 will leave that row byte-identical.
2. **Fix bug-032, but do not assume it explains the table.** The cross-encoder scores only a
   document's first 2048 chars and **36.9% of this corpus's answer-bearing turns sit beyond that
   offset** (896 turns: median 0, p75 3,268, p90 8,117). An earlier version of this list blamed
   `context`'s `single-session-preference` 0.200 on it; that was **wrong** — `rmx context` never
   constructs a reranker, so truncation cannot reach it. The exposed row is **`scan`'s 0.150**, and
   only if the hub's shared worker answered during the run at all. Check worker activity in the run
   window before claiming contamination (ch-bsd r2).
3. **Attribute the ~8.5 s CLI gap.** `build_context` warm is 0.45 s; the full daemonless CLI is
   9.0 s, of which only 2.8 s is CPU. That ~6 s of waiting is the real open performance question —
   NOT the retracted 62.9 s. See `workflow/measurements/longmemeval-latency.md`.
4. **Fix bug-030, re-run embed**, and add the dense and fused rows.
