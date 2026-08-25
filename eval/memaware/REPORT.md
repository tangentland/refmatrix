# MemAware Layer-A results — retrieval only, no LLM

90 questions (30/tier, seed 42), 1307 session documents, one rmx store built by
`ingest.py`. Metric: does the ranked list contain the question's
`answer_session_ids`? Deterministic, zero API cost. See README for why this
layer exists separately from upstream's continuity-accuracy harness.

All numbers below are at rmx **0.36.0**. The `context` row moved 20x between
first run and this one because the benchmark found three real defects in it;
the pre-fix figures are kept at the bottom.

## hit@20 — is the answer session anywhere in the top 20?

| method | easy | medium | hard | **overall** |
|---|---:|---:|---:|---:|
| bm25 (per session) | 0.667 | 0.533 | 0.133 | **0.444** |
| rmx context | 0.667 | 0.500 | 0.133 | **0.433** |
| rmx memory recall (dense) | 0.600 | 0.467 | 0.067 | **0.378** |
| rmx memory recall --fuse | 0.600 | 0.467 | 0.067 | **0.378** |
| rmx scan-prompt | 0.433 | 0.133 | 0.033 | **0.200** |
| bm25 (per day, upstream chunking) | 0.267 | 0.133 | 0.067 | **0.156** |

## MRR@20

| method | easy | medium | hard | **overall** |
|---|---:|---:|---:|---:|
| bm25 | 0.454 | 0.245 | 0.027 | **0.242** |
| rmx memory recall | 0.326 | 0.197 | 0.019 | **0.180** |
| rmx context | 0.247 | 0.185 | 0.029 | **0.153** |
| rmx scan-prompt | 0.109 | 0.019 | 0.002 | **0.043** |
| bm25 (per day) | 0.106 | 0.028 | 0.041 | **0.058** |

## hit@5 — what a k=5 injection would actually carry

| method | easy | medium | hard | **overall** |
|---|---:|---:|---:|---:|
| bm25 | 0.500 | 0.300 | 0.067 | **0.289** |
| rmx context | 0.367 | 0.300 | 0.067 | **0.244** |
| rmx memory recall | 0.467 | 0.233 | 0.033 | **0.244** |
| rmx scan-prompt | 0.233 | 0.033 | 0.000 | **0.089** |
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

## scan-prompt did not move

Identical scores before and after (0.200 hit@20), because `scan-prompt` reaches
the graph by its own concept-matching + PPR path rather than through
`_append_content_hits`. It remains the weakest rmx surface here and it is the
one the product actually ships on every prompt. Closing that gap — either by
giving scan-prompt the content-rank path or by understanding why its PPR walk
underperforms a BM25 bag of terms on prose — is the open question this
benchmark exists to answer.

## What has NOT been run

Layer B — upstream's continuity-accuracy harness — has never executed. It needs
an answer model and a judge; no Fireworks key, and the OpenAI key returns `429
You have no credits remaining`. `lib/llm.mjs` now routes `claude-*` to the
Anthropic Messages API, so one `ANTHROPIC_API_KEY` unblocks it. Run
`tools/smoke_judge.mjs` first.
