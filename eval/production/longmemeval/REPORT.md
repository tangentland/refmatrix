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
| retrieval depth | **50** |
| binary | deploy `rmx` 0.69.1, daemon up and warm |
| date | 2026-09-15 |

## Results — `restricted` mode {#restricted}

`restricted` = retrieve deep through the CLI, filter the ranked list to the question's own
~50-session haystack, cut to k. Comparable in SHAPE to published figures; see [[#not-comparable]].

| surface | MRR@20 | R@1 | R@5 | hit@5 | **ceiling** |
|---|---:|---:|---:|---:|---:|
| `context` | 0.679 | 0.476 | 0.605 | 0.683 | **0.683** |
| `scan` | 0.637 | 0.445 | 0.547 | 0.642 | **0.642** |

## THE RESULT IS SATURATED — read this before the table {#saturation}

`context` scores **hit@5 = 0.683 against a ceiling of 0.683**. `scan` scores 0.642 against 0.642.

The ceiling is the fraction of questions whose gold session appeared ANYWHERE in the depth-50 pool.
Hitting it exactly means **every gold session that entered the pool was ranked into the top 5**.

So these numbers do not measure ranking quality at all. They measure how often depth-50 retrieval
reached the gold session. **R@5 = 0.605 is a floor set by retrieval depth, not a ranking result.**
Raising `--depth` would raise both the ceiling and the score, and nothing about the ranker would
have changed.

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

Committed results: `eval/production/longmemeval/results/summary-symbolic-120.json`.

## Next, in priority order {#next}

1. **Re-run at `--depth 200`.** Until the ceiling is unsaturated these are not ranking numbers.
   ~4 h at current latency.
2. **Profile the 63 s.** Attribute it across BM25 fan-out, PPR walk, and rerank. Registered in the
   deferral registry; no cause is claimed without it.
3. **Fix bug-030, re-run embed**, and add the dense and fused rows.
