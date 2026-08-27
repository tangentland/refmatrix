# MemAware Layer-A results — retrieval only, no LLM

90 questions (30/tier, seed 42), 1307 session documents, one rmx store built by
`ingest.py`. Metric: does the ranked list contain the question's
`answer_session_ids`? Deterministic, zero API cost. See README for why this
layer exists separately from upstream's continuity-accuracy harness.

All numbers below are at rmx **0.37.0**, except the `+rerank` rows, which are
**0.42.0**. The `context` row moved 20x between first run and this one because
the benchmark found three real defects in it; the pre-fix figures are kept at
the bottom.

## hit@20 — is the answer session anywhere in the top 20?

| method | easy | medium | hard | **overall** |
|---|---:|---:|---:|---:|
| bm25 (per session) | 0.667 | 0.533 | 0.133 | **0.444** |
| rmx context | 0.667 | 0.500 | 0.133 | **0.433** |
| **rmx memory recall +rerank (0.42.0)** | 0.667 | 0.500 | 0.100 | **0.422** |
| rmx memory recall (dense) | 0.600 | 0.467 | 0.067 | **0.378** |
| rmx scan-prompt | 0.633 | 0.433 | 0.067 | **0.378** |
| rmx memory recall --fuse | 0.600 | 0.467 | 0.067 | **0.378** |
| bm25 (per day, upstream chunking) | 0.267 | 0.133 | 0.067 | **0.156** |
| LatticeDB 0.11.1 (BM25 FTS) | 0.100 | 0.133 | 0.033 | **0.089** |

## MRR@20

| method | easy | medium | hard | **overall** |
|---|---:|---:|---:|---:|
| bm25 | 0.454 | 0.245 | 0.027 | **0.242** |
| **rmx memory recall +rerank (0.42.0)** | 0.449 | 0.197 | 0.006 | **0.218** |
| rmx memory recall | 0.326 | 0.197 | 0.019 | **0.180** |
| rmx context | 0.247 | 0.185 | 0.029 | **0.153** |
| rmx scan-prompt | 0.266 | 0.157 | 0.023 | **0.149** |
| bm25 (per day) | 0.106 | 0.028 | 0.041 | **0.058** |

## hit@5 — what a k=5 injection would actually carry

| method | easy | medium | hard | **overall** |
|---|---:|---:|---:|---:|
| bm25 | 0.500 | 0.300 | 0.067 | **0.289** |
| **rmx memory recall +rerank (0.42.0)** | 0.533 | 0.333 | 0.000 | **0.289** |
| rmx context | 0.367 | 0.300 | 0.067 | **0.244** |
| rmx scan-prompt | 0.367 | 0.300 | 0.067 | **0.244** |
| rmx memory recall | 0.467 | 0.233 | 0.033 | **0.244** |
| bm25 (per day) | 0.133 | 0.033 | 0.033 | **0.067** |

Every method returned exactly 20 candidates (mean 19.9-20.0, no empties), so
the cutoffs compare like for like.

## Read this as: rmx loses here, and the reason is legible

**BM25 wins outright.** Not marginally — it beats rmx's best surface on every
tier. The direction was predicted (this corpus has no `calls`, `defines` or
`imports`; the structural graph that beats CodeRankEmbed on CodeSearchNet is
simply absent, leaving only the associative `mentions` layer) but the margin on
the medium tier is larger than "no structural edges" alone explains.

**The hard tier is unsolved by everything.** 0.133 for the best method, and
rmx's graph does not help: 0.033 for scan-prompt. Upstream's claim that
cross-domain implicit context needs a holistic overview rather than better
retrieval survives contact with a graph-based retriever. A co-mention walk
reaches "Ford Mustang air filter → Target coupons" only if some past session
put those in the same room; where the corpus never did, no graph invents it.

**Chunking was worth 2.8× on its own.** Per-session BM25 hit@20 0.444 vs
per-day 0.156. Upstream indexes 91 daily files — up to 858KB each — and then
truncates each retrieved file to 3000 characters, so even a correct day-level
hit usually shows the model none of the relevant session. A large part of the
published 2.8% BM25 baseline is that, not BM25.

**`--fuse` is a no-op at this scale.** Identical scores; the two ranking files
differ on 1 question of 90. Consistent with the prior finding that RRF fusion's
win is a scale effect.

## The `context` fixes (0.36.0) — before and after

| metric | before | after |
|---|---:|---:|
| hit@20 overall | 0.022 | **0.433** |
| MRR@20 overall | 0.007 | **0.153** |
| hit@20 easy | 0.033 | **0.667** |
| hit@20 medium | 0.033 | **0.500** |

`context` goes from worst method to level with BM25 on hit@20 (0.433 vs 0.444)
and ahead of the dense surface (0.378). It still trails BM25 badly on MRR
(0.153 vs 0.242): it finds the right session, it ranks it lower. That gap is
the next thing to chase and it is a ranking problem, which the earlier numbers
were too broken to expose.

## Three defects in `rmx context`, found by this run

`context` scoring 0.007 MRR while `memory recall` scores 0.180 over the same
store is not a ranking difference — the surface is broken for this input shape.

**1. `_ref_terms` applies no stoplist** (`context.py:756`; it drops only
1-character tokens). The grep floor runs `rg -F -i`, a fixed *substring*
match, so `are` — a stopword in `scan._PROMPT_STOPWORDS`, which this path never
consults — matches inside unrelated words and wins on match count. Live:

    rmx context "I need to vacuum under my bed today … my old sneakers …"
    → corpus/2023-04-30/d557e57a.md (w=191)
      tags: [memaw«are», session]

This is the fifth site of the same bug (see `feedback_reuse_shared_stoplist`).

**2. The grep floor matched substrings.** `rg -F -i` with no `-w`, ranked by
match count. Now word-boundary for multi-word refs only; identifier refs keep
substring matching, where finding `fov_wedge` inside `fov_wedge_polygon` is the
whole point of the floor.

**3. content_rank searched the half of the graph with no body index.** This was
the big one, and my first hypothesis for it — that the content path excluded
`kind=memory` — was WRONG. It passes `kinds=["code","doc","memory"]`. The real
shape is that a GMD doc becomes two entities and the body term-frequency sweep
hangs every `mentions` edge on the *node*, not the doc:

    answer_7e9ad7b4_2#root   kind=concept   hundreds of body-term edges
    answer_7e9ad7b4_2        kind=memory    5 edges

The ranked side was the one with five edges. Single-token refs appeared to work
only because they take the anchor path, which walks `mentions` directly. Fixed
by admitting `concept` to the kinds list, gated on `"#" in name` so a bare
concept — a query term, not a body — never becomes a result.

This affects every GMD-ingested memory in every store, not just this corpus.

## scan-prompt (0.37.0) — before and after

| metric | before | after |
|---|---:|---:|
| hit@20 overall | 0.200 | **0.378** |
| MRR@20 overall | 0.043 | **0.149** |
| hit@20 easy | 0.433 | **0.633** |
| hit@20 medium | 0.133 | **0.433** |

`scan-prompt` was the weakest rmx surface and it is the one that runs on every
prompt. Its per-concept bundles answer "what neighbours this term", once per
term, independently — a question with no idf and no coverage. A bundle ranks by
raw `mentions` weight (term frequency), so a COMMON prompt word with a high tf
outranks a RARE one with a low tf, and nothing prefers a document carrying
several prompt terms over one repeating a single term. Live, for a prompt about
vacuuming under a bed and old sneakers:

    === context for `vacuum` ===
      answer_8ee04a2e#root  (w=12)   …**Vacuum regularly**: Invest in a good…

Five such bundles, one per term, none able to notice that one session carried
both `sneakers` and `closet`. The fix was not new machinery: `content_rank`
already supplies idf + coverage, and the path was ALREADY in `scan_prompt` —
wired as a fallback for when no concept matched. On a corpus where every
content word is a concept it never ran. The case that needed it most was the
one case that could not reach it.

## Cross-encoder rerank (0.42.0) — buys the easy/medium tiers, costs the hard one

`RMX_RERANK` adds a cross-encoder pass (`ms-marco-MiniLM-L-12-v2`) over a 4x
over-fetched shortlist. Same retrieval, different ordering. Measured against the
same 90 questions, with `--no-rerank` reproducing the 0.37.0 `recall` row
*exactly* — so the baseline path is provably unchanged by 0.42.0 and this is a
clean A/B.

| metric | recall | recall +rerank | delta |
|---|---:|---:|---:|
| MRR@20 | 0.180 | **0.218** | +21% |
| hit@1 | 0.122 | **0.156** | +28% |
| hit@5 | 0.244 | **0.289** | +18% |
| hit@20 | 0.378 | **0.422** | +12% |
| Recall@20 | 0.315 | **0.357** | +13% |

It moves rerank-recall past dense and past scan-prompt on every cutoff, to
within 0.011 hit@20 of `context` and 0.022 of BM25 — and it does it on the
ordering, which is what the shortlist-precision argument predicted.

**But read the hard tier before believing the headline.** Rerank makes it worse:

| hard tier | recall | recall +rerank |
|---|---:|---:|
| MRR@20 | 0.019 | **0.006** |
| hit@5 | 0.033 | **0.000** |
| hit@20 | 0.067 | **0.100** |

Hard questions are the ones where the request and the answer session share no
keywords at all ("Ford Mustang air filter" -> "user redeems coupons at Target").
A cross-encoder is a semantic *matching* model; asked to rank a genuinely
non-matching pair it does exactly its job and pushes the answer down. hit@20
still improves there, but that is the 4x over-fetch, not the reranker — the
wider pool catches sessions retrieval was cutting off, and then the reranker
buries them below rank 5.

So the gain is real and the mechanism is the one claimed, but it is concentrated
where lexical/semantic overlap already exists. It does not touch the tier
upstream calls unsolved, and on the evidence here it cannot: that tier needs
association, and reranking is the opposite operation. Upstream's conclusion —
that this needs "a holistic view of the user's history" rather than a better
retriever — survives this result intact.

`--fuse` remains a no-op on this corpus (1 of 90 rankings differs from
non-fused, both before and after 0.42.0), so `recall-fuse-rr` is identical to
`recall-rr` and is not tabled separately.

`scan-prompt` and `context` do **not** run the rerank stage — it is wired into
`memory_recall` and `ann_search` only. Both were re-measured at 0.42.0 and are
unchanged (scan 0.149 MRR / 0.378 hit@20; context 0.433 hit@20), which also
confirms 0.42.0 introduced no regression on the surfaces it did not touch.
Extending rerank to scan-prompt is the obvious next experiment, and the hard-tier
result above is the reason to run it as an experiment rather than ship it.

## Where rmx still trails, after all three fixes

BM25 keeps the lead on every metric, and the gap is now concentrated in
RANKING, not retrieval: rmx surfaces have essentially closed hit@20 on easy
(0.667 vs 0.667) but sit at 0.149-0.180 MRR against BM25's 0.242. They find the
session and rank it lower. The hard tier is untouched by any of this — 0.133
best, and every rmx surface at 0.067 — which is the finding upstream predicted
and the one no amount of retrieval tuning addresses.

## LatticeDB as a fourth condition — the index is fine, the ranking is absent

[LatticeDB](https://github.com/jeffhajewski/latticedb) 0.11.1 puts BM25, HNSW
and graph traversal behind one transaction path in one file. refmatrix spreads
those across DuckDB + Lance + roaring bitmaps + a hand-rolled `facts.log`, and
most of its operational scars live on those seams, so "does the consolidated
engine retrieve better on the same corpus" is worth an hour rather than a
README reading. `tools/latticedb_rank.py` builds one FTS-indexed node per
session — same granularity as every other condition.

**Scope: BM25 only.** The vector path is deliberately untouched. LatticeDB
ships `hash_embed`, a hashing trick rather than a semantic embedding, so a
vector run against rmx's bge-small numbers would measure the embedder and
report it as the index. The honest version — load the SAME bge-small vectors
into both, compare recall and latency — is separate work.

### Every BM25 score comes back 0.0

Reproducible on a three-document database, across all three surfaces:

    fts_search("closet")        -> a:0.0000, b:0.0000
    fts_search_fuzzy("closet")  -> a:0.0000, b:0.0000
    Cypher  d.content @@ ...    -> matches, exposes no score column

The Python binding is not at fault: `database.py` reads a `ctypes.c_float`
out-param from `lattice_fts_result_get`, so the zero arrives from the native
side. Documentation calls this a "BM25-ranked inverted index" and the README
claims it is "~300x faster than SQLite FTS5"; on this build it returns the
right documents in no particular order.

### Which makes the headline number meaningless, so here is the one that isn't

With no scores, the top-k slice of a large matched set is arbitrary. Running
the same queries at k=500 separates *did the index find it* from *did the
engine rank it*:

| cutoff | easy | medium | hard | **overall** |
|---|---:|---:|---:|---:|
| hit@20 | 0.067 | 0.133 | 0.033 | **0.078** |
| hit@100 | 0.267 | 0.267 | 0.133 | **0.222** |
| hit@500 | 0.800 | 0.700 | 0.667 | **0.722** |

**The inverted index is good.** It contains the answer session for 72% of
questions — including 0.667 on the hard tier, where every other method sits at
0.067–0.133. It simply cannot say which of its matches matters. That is a
scoring bug, not a retrieval one, and it is presumably fixable in an afternoon
by whoever owns the Zig.

### One design choice, correctly documented, that a caller must handle

`@@` and `fts_search` are **conjunctive**: "All terms must match (implicit
AND)" (`book/src/cypher/full-text-search.md`). Handing it a raw 20-word
question therefore matches nothing — the first run returned a mean of **0.12**
documents per question. The ranker now stoplists the question through
refmatrix's own `scan._PROMPT_STOPWORDS` and backs off the conjunction until
something matches, which is what a real integration would do and keeps the
comparison about the engine. Not a defect; a contract.

### Timings

1307 sessions indexed in **20.3s** into a **175 MB** file. Query latency
**0.175 ms median** for a single term, **1.6 ms median / 4.2 ms p95** for the
backoff sequence at k=20. The speed claims that can be checked here hold up;
they are just attached to an index that does not rank.

## What has NOT been run

Layer B — upstream's continuity-accuracy harness — has never executed. It needs
an answer model and a judge; no Fireworks key, and the OpenAI key returns `429
You have no credits remaining`. `lib/llm.mjs` now routes `claude-*` to the
Anthropic Messages API, so one `ANTHROPIC_API_KEY` unblocks it. Run
`tools/smoke_judge.mjs` first.
