---
gmd: "0.1"
id: longmemeval-report
title: "LongMemEval on the production path — symbolic, dense and fused surfaces, 120 stratified questions"
tags: [eval, benchmark, longmemeval, plan-7, t0-6]
metadata:
  node_type: report
  created: 2026-09-15
  rmx_version: "0.84.0"
  updated: 2026-11-23
---

# LongMemEval, production path {#root}

rel: realizes -> [[task-7.4-plan-7-longmemeval]]
rel: realizes -> [[task-t0-suite-trust-sweep#t0-6]]
rel: part-of -> [[plan-7-longmemeval]]
rel: depends-on -> [[plan-review-2026-10-14#t11-folded-waves]]
rel: evidence-for -> [[longmemeval-latency]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]

**Every number here is depth-bound and must be read with its ceiling. See [[#saturation]] before
quoting anything.** Every row in [[#restricted]] and [[#union]] comes from ONE build (deploy `rmx`
0.84.0) in ONE run (2026-11-23). The 0.69.1 symbolic rows are kept, with their own provenance, in
[[#history-0-69-1]].

## Setup {#setup}

| | |
|---|---|
| dataset | `longmemeval_s` (HuggingFace `xiaowu0162/longmemeval`) |
| corpus | 19,829 unique session docs (25,112 haystack slots, deduped, 0 content conflicts) |
| graph | 406,886 concepts, 19,829 memory entities (`rmx stats`, 2026-11-23) |
| build | deploy `rmx` **0.84.0** (`~/bin/rmx`, deploy tree at `cab0a7dc`; `rmx version -v` read before the run) |
| store path taken | **opened, not rebuilt.** The 0.69.1-built store at `/Volumes/littlebig/longmemeval/.refmatrix` opened read-only under 0.84.0 (`rmx stats`, 2.6 s) and the embed resumed on it. Backed up first to `/Volumes/littlebig/longmemeval-store-backup-2026-11-23/` (9.5 GB, 9,945,432 KB, file listing identical) |
| build command | `python3 ingest.py --rmx ~/bin/rmx --skip init --skip ingest-gmd` (embed, compile preview, stats) |
| **embed wall time** | **997.4 s** (16m37s) for 19,829 memory rows, 78 batches of 256, no failure |
| compile | preview only (`rmx memory compile` without `--apply`, 8.4 s); nothing written |
| daemon | **none.** The harness starts no daemon, so every `rmx` call ran daemonless. No launchd job exists for this store; no `rmxd.pid` or socket appeared |
| model workers | **the hub's shared workers** (`~/.refmatrix/models.sock`): embed pid 78831, rerank pid 78880, both children of hub pid 78825, sampled every 120 s across the run (21 samples) |
| read snapshot | daemonless reads open `catalog.read.duckdb`, the snapshot the 0.69.1 daemon took 2026-09-15 20:37; the embed wrote the active slot (`catalog.A`) and `vectors/`. The symbolic rows read the same graph the 0.69.1 rows read, through 0.84.0 code |
| questions scored | **120** — type-stratified, 20 per type, seed 42 (`subsets/stratified-20.json`) |
| retrieval depth | **50** for `context` and the four `recall` surfaces; **`scan` is DEPTH-UNCONTROLLED** (see [[#saturation]]) |
| scoring | both modes, `--at 1,5,10,20`; 0 failed questions on every surface |
| run command | `python3 run.py --rmx ~/bin/rmx --subset 20 --depth 50 --at 1,5,10,20 --workers 4 --mode union --mode restricted --method recall --method recall-fuse --method recall-rr --method recall-fuse-rr --method context --method scan` |
| run window | 2026-11-24T01:03:10Z to 01:43:19Z (2026-11-23 local): build 1,009 s, retrieval 1,400 s |
| date | 2026-11-23 |

`REFMATRIX_ROOT` was pinned per `rmx` process by `paths.rmx_env`, never exported. `rmx hub status`
read the same before and after the run (8 stores, all `restarts=0`, v0.84.0).

Committed results: `eval/production/longmemeval/results/summary-120-0.84.0.json`, run.py's
`summary.json` copied verbatim (sha256 `8584b291…f85f6ae`) plus a `_provenance` key.

## Results — `restricted` mode {#restricted}

`restricted` = retrieve deep through the CLI, filter the ranked list to the question's own
~50-session haystack, cut to k. Comparable in SHAPE to published figures; see [[#not-comparable]].

| surface | MRR@20 | R@1 | R@5 | R@20 | hit@5 | hit@20 | **ceiling** | saturated |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `context` | 0.679 | 0.476 | 0.605 | 0.605 | 0.683 | 0.683 | **0.683** | yes |
| `scan` * | 0.637 | 0.445 | 0.547 | 0.547 | 0.642 | 0.642 | **0.642** | yes |
| `recall` | 0.596 | 0.421 | 0.515 | 0.515 | 0.608 | 0.608 | **0.608** | yes |
| `recall-fuse` † | 0.596 | 0.421 | 0.515 | 0.515 | 0.608 | 0.608 | **0.608** | yes |
| `recall-rr` | 0.613 | 0.423 | 0.527 | 0.527 | 0.625 | 0.625 | **0.625** | yes |
| `recall-fuse-rr` ‡ | 0.604 | 0.429 | 0.513 | 0.513 | 0.608 | 0.608 | **0.608** | yes |

\* `scan` is DEPTH-UNCONTROLLED — its ceiling is scan-prompt's default pool, NOT a depth-50 pool.
Do not read it against the depth-50 rows as though one knob produced both.

† `recall-fuse` = `recall`: the symbolic leg is empty on this corpus ([[#fusion]], bug-300). No
fusion claim is made from this row.

‡ `recall-fuse-rr` differs from `recall-rr` because the hybrid path widens the dense pool
(k = max(k, rrf_k)) before the rerank, not because of fusion ([[#fusion]]).

`recall-rr`'s ceiling (0.625) differs from `recall`'s (0.608): the reranked call returned a
different depth-50 list. The mechanism is not measured here.

## THE RESULT IS SATURATED — read this before the table {#saturation}

Every restricted row scores **hit@5 equal to its ceiling** (the `saturated` column). The ceiling is
the fraction of questions whose gold session appeared ANYWHERE in the retrieved pool. Hitting it
exactly means **every gold session that entered the pool was ranked into the top 5**. So no row
measures ranking quality. Each measures how often retrieval reached the gold session at all. The
dense rows are labelled by the same rule as the symbolic rows.

**The rows are bounded by DIFFERENT things:**

- `context` and the four `recall` surfaces — pool = depth 50 (`--max-entities 50`, `-k 50`).
  **R@5 is a floor set by retrieval depth.** Raising `--depth` raises both ceiling and score with
  no change to the ranker.
- `scan` — **DEPTH-UNCONTROLLED.** `--depth` never reached it: `--max-tokens` is inert in JSON
  mode and `scan.py` cuts at `matches[:max_concepts]` before budgeting (measured, ch-bsd r2
  #b-6-r2). Its 0.642 is scan-prompt's DEFAULT pool, and `--depth 200` will not move it.

So the dense surfaces' lower R@5 (0.515 vs `context`'s 0.605) is, on this evidence, a lower
ceiling at depth 50 (0.608 vs 0.683): dense reached the gold session less often, and ranked
everything it reached into the top 5, as `context` did.

## Per question type {#per-type}

Restricted R@5, 20 questions per type:

| type | `context` | `scan` | `recall` | `recall-fuse` † | `recall-rr` | `recall-fuse-rr` ‡ |
|---|---:|---:|---:|---:|---:|---:|
| single-session-assistant | 0.950 | 0.950 | 0.950 | 0.950 | 0.950 | 0.950 |
| knowledge-update | 0.925 | 0.800 | 0.300 | 0.300 | 0.275 | 0.325 |
| multi-session | 0.567 | 0.454 | 0.588 | 0.588 | 0.650 | 0.637 |
| single-session-user | 0.500 | 0.450 | 0.300 | 0.300 | 0.300 | 0.250 |
| temporal-reasoning | 0.487 | 0.477 | 0.502 | 0.502 | 0.537 | 0.517 |
| **single-session-preference** | **0.200** | **0.150** | **0.450** | **0.450** | **0.450** | **0.400** |

**The surfaces fail on different questions.** Dense recall more than doubles symbolic on
preference (0.450 vs 0.200). A preference is stated once, casually, in vocabulary that never
recurs, so the `mentions` index has nothing to grip. Dense is also ahead on multi-session
(0.588–0.650 vs 0.567) and temporal-reasoning (0.502–0.537 vs 0.487), the two types the
conceptual-memory thesis predicts the system should win. It falls far behind on knowledge-update
(0.275–0.325 vs 0.925) and single-session-user (0.250–0.300 vs 0.500). A working fusion would
exploit that split; on this corpus fusion does not run ([[#fusion]]).

This corpus has **no structural edges at all** — no calls, defines, or imports — so the half of
the graph that wins CSN is absent by construction. That is an explanation, not a defence: a memory
product meets prose corpora in the field.

## `union` vs `restricted` {#union}

`union` scores the ranked list against all 19,829 sessions: the gold session has to beat every
other question's haystack. The ceiling is the same pool's: the fraction of questions whose gold
session appears anywhere in the retrieved list. It bounds `union` hit@k at every k as it bounds
`restricted`. No union row is saturated (hit@20 is below the ceiling on every surface).

| surface | MRR@20 | R@1 | R@5 | R@20 | hit@5 | hit@20 | **ceiling** |
|---|---:|---:|---:|---:|---:|---:|---:|
| `context` | 0.421 | 0.275 | 0.411 | 0.553 | 0.492 | 0.608 | 0.683 |
| `scan` * | 0.439 | 0.278 | 0.465 | 0.519 | 0.542 | 0.600 | 0.642 |
| `recall` | 0.231 | 0.127 | 0.239 | 0.362 | 0.308 | 0.458 | 0.608 |
| `recall-fuse` † | 0.231 | 0.127 | 0.239 | 0.362 | 0.308 | 0.458 | 0.608 |
| `recall-rr` | 0.282 | 0.162 | 0.266 | 0.401 | 0.342 | 0.492 | 0.625 |
| `recall-fuse-rr` ‡ | 0.312 | 0.185 | 0.298 | 0.427 | 0.367 | 0.517 | 0.608 |

`context` union completed this time (it did not in the 0.69.1 batch). Union R@5 is below restricted
for every surface; the dense surfaces lose the most (0.239 vs 0.515), the symbolic ones less
(`context` 0.411 vs 0.605, `scan` 0.465 vs 0.547).

## `--fuse` is a no-op on this corpus {#fusion}

`recall` and `recall-fuse` returned byte-identical rankings for 120 of 120 questions
(`results/rank-recall.json` equals `results/rank-recall-fuse.json` on the data volume). The lead
traced it (bug-300 in `workflow/bug_registry.md`): the flag runs, but its symbolic leg,
`content_rank(terms, kinds=['memory'])`, returned `[]` for 40 of 40 LongMemEval questions probed.
A memory entity's `mentions` edges hold only its title and tag words. These memories are titled by
session id, so their mentions are `session`, `longmemeval` and ids, and the body words sit on GMD
block nodes (`kind=concept`) that the leg filters out. RRF over the dense list alone keeps the
dense order. A second defect reaches the same leg: `content_terms` keeps trailing punctuation
(`work?`, `with?`), so a question's last word never resolves to its concept (bug-301).

Therefore:

- the `recall-fuse` rows are dense rows, and **no figure here is a fusion result**;
- `recall-fuse-rr` differs from `recall-rr` only through the hybrid's wider dense pool
  (k = max(k, rrf_k)) feeding the reranker.

The "RRF dense⊕symbolic recall fusion" measurement in `docs/PERFORMANCE.md`
([[refmatrix/PERFORMANCE#negatives]]) came from the memory-recall eval over descriptively titled
memories; it does not transfer to this corpus until bug-300 is fixed.

## Latency — RETRACTED, see the profile {#latency}

An earlier version of this report claimed `rmx context` costs **62.9 s** per query here and that
rmx is ~4,500x slower than agentmemory's published 14 ms. **That is retracted.** The number was
measured while the daemon was building a 432 MB adjacency cache and replicating three 2.4 GB
catalog slots — a storm window reported as steady state.

Profiled 2026-09-16: `build_context` warm is **0.45 s**, of which BM25 over 406,885 concepts plus
the graph walk is **0.37 s**. The retrieval core is not slow. What remains unexplained is an ~8.5 s
gap between `build_context` (0.45 s) and the full daemonless CLI (9.0 s), of which only 2.8 s is
CPU. That gap is not yet attributed.

The 2026-11-23 run's `retrieve_s` per method (120 questions, 4 workers, daemonless: `context`
50.1 s, `scan` 1,077.3 s, `recall` 33.6 s, `recall-rr` 90.6 s) is a batch wall clock on a shared
machine, not a per-query latency. **No per-query latency figure for this corpus should be
quoted** until the store is re-measured quiet. Full retraction and decomposition:
`workflow/measurements/longmemeval-latency.md`.

## NOT comparable to published figures {#not-comparable}

External landmarks, quoted as landmarks and nothing more — different harness, embedding model,
chunking, and haystack scoping:

| system | claimed |
|---|---|
| agentmemory | 95.2% R@5 on LongMemEval-S, 500 questions |
| mcp-memory-service | 80.4% R@5, 89.1% MRR; multi-session 70.7%, temporal-reasoning 72.0% |

**Do not put 0.605 or 0.515 beside 95.2%.** Three reasons, each sufficient: this run is depth-50 SATURATED;
`restricted` is a post-hoc filter, not a per-question index (no CLI exposes
`ann_search(candidate_ids=...)`); and neither published figure states its haystack scoping.

## The dense half: the embed now completes {#embed}

**Result (2026-11-23, 0.84.0).** `rmx embed --kinds memory` embedded all 19,829 memory rows in
**997.4 s** through the hub's shared embed worker, with no failure and no retry. It ran as
`ingest.py --skip init --skip ingest-gmd` on the persisted 0.69.1 store, so the 4h23m ingest was
not repeated. The four dense and fused surfaces are in [[#restricted]] and [[#union]]; read the
fuse rows through [[#fusion]]. This closes wave item **W2-c**
([[plan-review-2026-10-14#t11-folded-waves]]).

**History.** On 2026-09-15 (0.69.1) the same pass failed after 30.8 s on a model-worker socket
`TimeoutError`, aborting the build before `memory compile`. The cause was the fleet's work budget
(`SHARED_OP_TIMEOUT_S` = 30 s) sitting below its own qualifying budget (`PROBE_TIMEOUT_S` = 45 s)
and below a cold worker's model load. **bug-030 was fixed 2026-09-16 in `464485d`** (the op
budget is floored at the probe budget). A first diagnosis, blaming `WorkerClient.call(timeout=X)`
for leaking a probe timeout onto the persistent socket, was refuted and withdrawn on 2026-10-19
(W1-d): that leak was already fixed in `d576a81`, and the leaked budget (45 s) was longer than the
one that expired (30 s). See the bug-030 row in `workflow/bug_registry.md`.

## Reproduce {#reproduce}

```bash
cd eval/production/longmemeval
hf download xiaowu0162/longmemeval longmemeval_s --repo-type dataset --local-dir <data>/upstream  # once, by hand (paths.py: HF_REPO, SPLITS)
python3 prepare.py --split s --per-type 20
python3 ingest.py                                  # full build; on a persisted store instead:
python3 ingest.py --skip init --skip ingest-gmd    # embed, compile preview, stats
python3 run.py --subset 20 --depth 50 --at 1,5,10,20 --workers 4 \
    --method context --method scan --method recall --method recall-fuse \
    --method recall-rr --method recall-fuse-rr
```

`paths.rmx_env` pins `REFMATRIX_ROOT` to `<data>/.refmatrix` for each `rmx` call; do not export
it. `--depth 50` applies to `context` and the `recall` surfaces; `scan` ignores it and records
`depth: null`.

## History: the 0.69.1 symbolic rows (2026-09-15) {#history-0-69-1}

Kept as taken, with their original provenance; do not mix them into the tables above. Build:
deploy `rmx` 0.69.1, daemon up and warm, `rmx init` → `ingest-gmd --as-memory` (15,775 s, 4h23m)
→ embed FAILED (bug-030). Graph: 406,885 concepts, 2.53 GB catalog. 120 questions (20 per type,
seed 42), depth 50 for `context`, `scan` depth-uncontrolled. Date 2026-09-15. Results:
`eval/production/longmemeval/results/summary-symbolic-120.json`.

| surface | MRR@20 | R@1 | R@5 | hit@5 | **ceiling** |
|---|---:|---:|---:|---:|---:|
| `context` | 0.679 | 0.476 | 0.605 | 0.683 | **0.683** |
| `scan` * | 0.637 | 0.445 | 0.547 | 0.642 | **0.642** |

`scan` union R@5 was 0.465; `context` union did not complete in that batch. Per-type R@5
(`context` / `scan`): single-session-assistant 0.950 / 0.950, knowledge-update 0.925 / 0.800,
multi-session 0.567 / 0.454, single-session-user 0.500 / 0.450, temporal-reasoning 0.487 / 0.477,
single-session-preference 0.200 / 0.150.

The 0.84.0 re-take reproduces both restricted rows, `scan`'s union R@5 and every per-type figure
to three decimals. Both runs read the same graph (the 2026-09-15 read snapshot; see [[#setup]]).

## Next, in priority order {#next}

1. **Re-run at `--depth 200`.** Until the ceiling is unsaturated these are not ranking numbers.
   Runtime unknown — the "~4 h" an earlier version of this list gave was derived from the retracted
   62.9 s figure and is withdrawn with it. **`--depth` reaches `context` and the `recall`
   surfaces, not `scan`.** b-6 was NOT fixed: two attempted fixes were both inert and a third
   guess was declined (ch-bsd r1 #b-6, r2 #b-6-r2), so `scan` is permanently DEPTH-UNCONTROLLED,
   its 0.642 is scan-prompt's DEFAULT pool, and re-running at 200 will leave that row
   byte-identical. Not part of W2-c.
2. **Fix bug-032, but do not assume it explains the table.** The cross-encoder scores only a
   document's first 2048 chars and **36.9% of this corpus's answer-bearing turns sit beyond that
   offset** (896 turns: median 0, p75 3,268, p90 8,117). `rmx context` never constructs a
   reranker, so truncation cannot reach it. The exposed rows are `scan` and the two `-rr` rows.
   `recall-rr`'s rankings differ from `recall`'s on 34 of 120 questions, so the reranker answered
   in this run;
   the hub's shared rerank worker (pid 78880) went from 0.66 GB RSS before the `-rr` window to
   1.42–1.53 GB in it (01:23Z, 01:25Z samples). It serves the whole fleet, so that is consistent
   with these calls, not proof that only they drove it.
3. **Attribute the ~8.5 s CLI gap.** `build_context` warm is 0.45 s; the full daemonless CLI is
   9.0 s, of which only 2.8 s is CPU. That ~6 s of waiting is the real open performance question —
   NOT the retracted 62.9 s. See `workflow/measurements/longmemeval-latency.md`.
4. ~~**Re-run embed and add the dense and fused rows.**~~ **Closed 2026-11-23 by T0.6**
   ([[task-t0-suite-trust-sweep#t0-6]]): the embed completed in 997.4 s on 0.84.0 and the four
   rows are in [[#restricted]] and [[#union]] (W2-c).
5. **Fix bug-300 and bug-301, then re-run the fuse rows.** Until the memory BM25 leg sees body
   text and the tokenizer drops trailing punctuation, `--fuse` is dense on this corpus. The
   per-type split in [[#per-type]] (dense wins preference, symbolic wins knowledge-update) is what
   a working fusion would exploit.
