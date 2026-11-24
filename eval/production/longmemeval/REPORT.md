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
0.84.0) on ONE store. Eight rows are from the 2026-11-23 run; the two `-rr` rows are from the
bug-303 re-runs of 2026-11-24 at one worker ([[#rerank-rerun]]). The 0.69.1 symbolic rows are
kept, with their own provenance, in [[#history-0-69-1]].

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
| scoring | both modes, `--at 1,5,10,20`; 0 failed questions on every surface; `_meta.n_reranked` on each `-rr` surface |
| run command | `python3 run.py --rmx ~/bin/rmx --subset 20 --depth 50 --at 1,5,10,20 --workers 4 --mode union --mode restricted --method recall --method recall-fuse --method recall-rr --method recall-fuse-rr --method context --method scan` |
| run window | 2026-11-24T01:03:10Z to 01:43:19Z (2026-11-23 local): build 1,009 s, retrieval 1,400 s |
| `-rr` re-runs | harness `cc6ea811` (bug-303), `--workers 1`, same store and build: `recall-rr` 02:19:26Z to 02:29:39Z (reranked 120/120); `recall-fuse-rr` 02:30:57Z to 02:36:07Z (reranked 119/120). See [[#rerank-rerun]] |
| date | 2026-11-23 |

`REFMATRIX_ROOT` was pinned per `rmx` process by `paths.rmx_env`, never exported. `rmx hub status`
read the same before and after the run (8 stores, all `restarts=0`, v0.84.0).

Committed results: `eval/production/longmemeval/results/summary-120-0.84.0.json`, run.py's
`summary.json` copied verbatim plus a `_provenance` key. The source is the data volume's
`summary.json` after the `-rr` entries were replaced by the re-runs' (sha256 `ea77f56f…adda41`;
the 2026-11-23 run's was `8584b291…f85f6ae`).

## Results — `restricted` mode {#restricted}

`restricted` = retrieve deep through the CLI, filter the ranked list to the question's own
~50-session haystack, cut to k. Comparable in SHAPE to published figures; see [[#not-comparable]].

| surface | MRR@20 | R@1 | R@5 | R@20 | hit@5 | hit@20 | **ceiling** | saturated |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `context` | 0.679 | 0.476 | 0.605 | 0.605 | 0.683 | 0.683 | **0.683** | yes |
| `scan` * | 0.637 | 0.445 | 0.547 | 0.547 | 0.642 | 0.642 | **0.642** | yes |
| `recall` | 0.596 | 0.421 | 0.515 | 0.515 | 0.608 | 0.608 | **0.608** | yes |
| `recall-fuse` † | 0.596 | 0.421 | 0.515 | 0.515 | 0.608 | 0.608 | **0.608** | yes |
| `recall-rr` | 0.637 | 0.440 | 0.541 | 0.541 | 0.642 | 0.642 | **0.642** | yes |
| `recall-fuse-rr` ‡ (reranked 119/120) | 0.637 | 0.440 | 0.541 | 0.541 | 0.642 | 0.642 | **0.642** | yes |

\* `scan` is DEPTH-UNCONTROLLED — its ceiling is scan-prompt's default pool, NOT a depth-50 pool.
Do not read it against the depth-50 rows as though one knob produced both.

† `recall-fuse` = `recall`: the symbolic leg is empty on this corpus ([[#fusion]], bug-300). No
fusion claim is made from this row.

‡ `recall-fuse-rr` = `recall-rr` for the same reason (bug-300): 119 of 120 rankings identical and
every cell equal. Its rerank was skipped on one question, so it is labelled reranked 119/120
([[#rerank-rerun]]). No fusion claim is made from this row.

The `-rr` ceiling (0.642) is above `recall`'s (0.608) because a reranked call does not return the
same depth-50 list: read from the deploy code (`recall.replica_memory_recall`), `--rerank` draws
`min(max(k, 2k), 100)` = 100 dense candidates and the cross-encoder returns its top 50 of them, so
gold from dense ranks 51-100 can enter the pool. That mechanism is a code reading. The net is
measured (bsd-t06 confirm-lite, from the rank files): against `recall`'s depth-50 list, the
reranked list gains gold on 7 questions and loses it on 3, net +4 of 120 (0.608 → 0.642); the
ceiling is not only inflow.

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

| type | `context` | `scan` | `recall` | `recall-fuse` † | `recall-rr` | `recall-fuse-rr` ‡ (reranked 119/120) |
|---|---:|---:|---:|---:|---:|---:|
| single-session-assistant | 0.950 | 0.950 | 0.950 | 0.950 | 1.000 | 1.000 |
| knowledge-update | 0.925 | 0.800 | 0.300 | 0.300 | 0.325 | 0.325 |
| multi-session | 0.567 | 0.454 | 0.588 | 0.588 | 0.742 | 0.742 |
| single-session-user | 0.500 | 0.450 | 0.300 | 0.300 | 0.250 | 0.250 |
| temporal-reasoning | 0.487 | 0.477 | 0.502 | 0.502 | 0.527 | 0.527 |
| **single-session-preference** | **0.200** | **0.150** | **0.450** | **0.450** | **0.400** | **0.400** |

**The surfaces fail on different questions.** Dense recall more than doubles symbolic on
preference (0.450 vs 0.200). A preference is stated once, casually, in vocabulary that never
recurs, so the `mentions` index has nothing to grip. Dense is also ahead on multi-session
(0.588–0.742 vs 0.567) and temporal-reasoning (0.502–0.527 vs 0.487), the two types the
conceptual-memory thesis predicts the system should win. It falls far behind on knowledge-update
(0.300–0.325 vs 0.925) and single-session-user (0.250–0.300 vs 0.500). A working fusion would
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
| `recall-rr` | 0.348 | 0.200 | 0.327 | 0.445 | 0.408 | 0.558 | 0.642 |
| `recall-fuse-rr` ‡ (reranked 119/120) | 0.348 | 0.200 | 0.327 | 0.445 | 0.408 | 0.558 | 0.642 |

`context` union reproduces the 0.69.1 batch's (`summary-symbolic-120.json`: MRR 0.421, R@1 0.275,
R@5 0.411, hit@5 0.492); only overall R@20 moved (0.553 vs 0.549). `scan` union reproduces R@5
0.465 but not MRR or R@1 (0.439 vs 0.444, 0.278 vs 0.282). Union R@5 is below restricted for every
surface; the dense surfaces lose the most (`recall` 0.239 vs 0.515, the reranked rows 0.327 vs
0.541), the symbolic ones less (`context` 0.411 vs 0.605, `scan` 0.465 vs 0.547).

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
- `recall-fuse-rr` is `recall-rr` by the same cause: with the rerank on, both paths draw the same
  100-candidate dense pool (`hybrid_recall`'s `max(k, rrf_k)` is `max(100, 60)` = 100), the empty
  symbolic leg leaves it in dense order, and the cross-encoder reorders it identically. Measured:
  119 of 120 rankings identical; the one that differs (`6b168ec8`) is the question whose rerank
  was skipped ([[#rerank-rerun]]). The 2026-11-23 text said the two differed through a "wider
  dense pool"; that was false (bsd-t06 r1 #b-2). Their gap that day came from which questions the
  rerank skipped (bug-303).

The "RRF dense⊕symbolic recall fusion" measurement in `docs/PERFORMANCE.md`
([[refmatrix/PERFORMANCE#negatives]]) came from the memory-recall eval over descriptively titled
memories; it does not transfer to this corpus until bug-300 is fixed.

## The `-rr` re-runs: how many answers were reranked {#rerank-rerun}

The 2026-11-23 run published `recall-rr` and `recall-fuse-rr` as rerank rows, but `run.py` kept only
ids: `memory recall --json` prints a bare list and says a skipped rerank only on stderr
(`# rmx: warning: rerank skipped: …; hits unreranked`, exit 0). At `--workers 4`, `recall-rr`
equalled `recall`'s dense top 50 on 86 of 120 questions (bsd-t06 r1 #b-1, bug-303). The harness now
records, per `-rr` surface, `n_reranked`, `n_rerank_skipped`, `unreranked_ids` and every distinct
warning in `_meta` (`cc6ea811`), and `tests/test_eval_artifact_cited.py` requires every cited cell
of a row reranked on fewer than all questions to carry its fraction.

| run (2026-11-24, `--workers 1`) | surface | reranked | skipped ids |
|---|---|---:|---|
| r2, 02:19:26Z to 02:29:39Z | `recall-rr` | **120/120** | none |
| r2 | `recall-fuse-rr` | 118/120 | `7405e8b1`, `75832dbd` |
| r3, 02:30:57Z to 02:36:07Z (one surface) | `recall-fuse-rr` | **119/120** | `6b168ec8` |

The tables take `recall-rr` from r2 and `recall-fuse-rr` from r3 (L196: re-run once, then label
the true fraction). Each skip printed exactly `rerank skipped: TimeoutError: timed out; hits
unreranked`, and each skipped answer is byte-identical to `recall`'s dense top 50. The skipped
calls took about 2.0 s (r2: 2,029 ms and 2,039 ms; r3: 1,904 ms); they did not wait out the 30 s
rerank budget. The timing alone does not separate a skip from a rerank: the same questions took
2.02-2.09 s when they were reranked in the other run. What places the skip is the warning text:
`rerank skipped: TimeoutError: timed out` is raised only inside `reranker.shared_reranker`'s
try block, i.e. by the connect to the hub's shared rerank worker (one process for the whole
fleet) or by its 1 s `RERANK_PROBE_S` probe, and the deployed code turns it into the dense
fallback. **Which of the two timed out, and why, is not measured** (bug-306).
The probe keeps its deployed default here: the benchmark path is the production path. `rmx hub
status` read the same before and after each re-run.

## Latency — RETRACTED, see the profile {#latency}

An earlier version of this report claimed `rmx context` costs **62.9 s** per query here and that
rmx is ~4,500x slower than agentmemory's published 14 ms. **That is retracted.** The number was
measured while the daemon was building a 432 MB adjacency cache and replicating three 2.4 GB
catalog slots — a storm window reported as steady state.

Profiled 2026-09-16: `build_context` warm is **0.45 s**, of which BM25 over 406,885 concepts plus
the graph walk is **0.37 s**. The retrieval core is not slow. What remains unexplained is an ~8.5 s
gap between `build_context` (0.45 s) and the full daemonless CLI (9.0 s), of which only 2.8 s is
CPU. That gap is not yet attributed.

The `retrieve_s` per method (120 questions, daemonless; 2026-11-23 at 4 workers: `context`
50.1 s, `scan` 1,077.3 s, `recall` 33.6 s; the 2026-11-24 `-rr` re-runs at 1 worker: `recall-rr`
254.9 s, `recall-fuse-rr` 309.2 s) is a batch wall clock on a shared machine, not a per-query
latency. **No per-query latency figure for this corpus should be
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

Union R@5 was 0.411 for `context` and 0.465 for `scan` (`summary-symbolic-120.json`). Per-type R@5
(`context` / `scan`): single-session-assistant 0.950 / 0.950, knowledge-update 0.925 / 0.800,
multi-session 0.567 / 0.454, single-session-user 0.500 / 0.450, temporal-reasoning 0.487 / 0.477,
single-session-preference 0.200 / 0.150.

The 0.84.0 re-take reproduces both restricted rows, both union R@5 figures and every per-type
figure to three decimals. Both runs read the same graph (the 2026-09-15 read snapshot; see [[#setup]]).

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
   That the reranker answered is read from the artifact, not from how many rankings moved: the
   2026-11-23 reading ("differ from `recall`'s on 34 of 120, so the reranker answered") had it
   backwards, since the other 86 were unreranked (bug-303). After the re-runs `_meta.n_reranked`
   is 120/120 for `recall-rr` and 119/120 for `recall-fuse-rr` ([[#rerank-rerun]]), and
   `recall-rr` equals `recall` on 0 of 120.
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
