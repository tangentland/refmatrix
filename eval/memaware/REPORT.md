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

## Prompt-concept expansion (0.43.0) — and why the headline barely moves

Three changes to how a prompt becomes concepts, measured on the same 90
questions.

1. **Canonical-variant resolution.** `match_concepts` resolved by exact name
   only. `resolve_concept_ids` folds camel/snake/dash/digit-boundary forms via
   `canonical_name`, and `store.py` documents it as "used by the
   query/context/neighbors path so an LLM passing any surface form lands on the
   same set" — scan-prompt, the always-on hook, was the one read surface that
   skipped it.
2. **Prompt-coverage on concept selection.** `content_rank` multiplies entity
   scores by `(covered_terms / n_terms) ** 3`, the single largest win in the
   CSN stack. Concept *selection* never used it: bundles went to the
   highest-salience concepts, and salience knows nothing about the rest of the
   prompt. Now a seed is boosted by how much its neighborhood overlaps the
   other seeds'.
3. **A prompt clique before the PPR walk.** Seeding PPR on several concepts is
   not the same as linking them: joint seeding sums independent diffusions, so
   mass never flows *through* one prompt concept to another's neighborhood. A
   weighted clique changes the topology. The justification is the one ingest
   already uses — co-occurrence in a document is written as a co-mention edge,
   and a prompt is a document.

### Isolated concept path (`--no-content`)

| config | MRR@20 | hit@5 | hit@20 | Recall@20 |
|---|---:|---:|---:|---:|
| baseline | 0.043 | 0.089 | 0.200 | 0.132 |
| coverage only | 0.047 | 0.100 | 0.222 | 0.155 |
| clique only | 0.044 | 0.089 | **0.178** | 0.144 |
| clique + coverage | 0.052 | 0.111 | 0.222 | 0.169 |
| **all three** | **0.065** | **0.144** | **0.267** | **0.206** |

hit@20 +34%, Recall@20 +56%, MRR +51%.

**The clique is negative on its own** (0.200 → 0.178) and positive only with
coverage. That is the predicted failure mode arriving on schedule: a clique
gives any junk seed surviving the salience gate a path into every other seed's
neighborhood, and coverage is what demotes the seed that shares nothing with
the rest of the prompt. They ship together or not at all; enabling one without
the other ships a known regression.

### Full pipeline — the honest number

| config | MRR@20 | hit@20 | Recall@20 | hard hit@20 |
|---|---:|---:|---:|---:|
| baseline | 0.149 | 0.378 | 0.300 | 0.067 |
| variants + coverage | 0.149 | 0.378 | 0.291 | 0.100 |
| variants + clique | 0.148 | 0.367 | 0.286 | 0.100 |
| **all three** | **0.150** | **0.389** | **0.303** | **0.100** |

hit@20 0.378 → 0.389 is **one question out of 90**. MRR is flat. Taken alone
this is within noise, and it would be wrong to call it a win.

The isolation explains why: the content bundle is emitted first and already
finds most of what the improved concept path finds, so the concept-path gain
is largely redundant *on this corpus*. The pre-0.37.0 concept-only score was
0.200 hit@20 — exactly the isolated baseline here — and content fusion is what
took the surface to 0.378. Concept selection has been the junior partner ever
since.

That makes the case for shipping these a structural one rather than a metric
one: the changes are correct (a read surface that skipped variant expansion was
a bug), they cost nothing measurable, and they matter wherever the content
bundle is weak — short prompts with few content words, and code corpora where
identifier structure carries what BM25-over-prose cannot. MemAware is prose
only, so it is close to the worst case for exactly these three.

Flags: `RMX_SCAN_VARIANTS`, `RMX_SCAN_COVERAGE_ALPHA` (default 3, measured
identical at 1), `RMX_SCAN_CLIQUE_W` (default 2.0). `scan-nocontent` is a
condition in `retrieval_eval.py` for reproducing the isolation.

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

## Multi-word phrases: measured, and closed (2026-09-03)

Skip-pair `phrase/*` concepts wired into the prose path (`ingest_gmd`), A/B'd
against the identical corpus with only `RMX_INGEST_PHRASES` differing. Both
arms built from scratch under `/Volumes/littlebig/ab/{base,phrase}/memaware`,
1307 docs, 90 questions.

| surface | metric | unigram | +phrases |
|---|---|---:|---:|
| context | MRR | 0.159 | 0.160 |
| context | hit@10 | 0.344 | 0.322 |
| context | hit@20 | 0.422 | 0.422 |
| scan | MRR | 0.240 | 0.225 |
| scan | hit@1 | 0.189 | 0.178 |
| scan | hit@5 | 0.300 | 0.278 |
| scan | hit@20 | 0.389 | 0.389 |

**hit@20 is identical on both surfaces.** That is the finding, not the small
MRR losses. A phrase key's constituent words are already `mentions` on the same
node, so pairs cannot surface a session the unigrams missed — the candidate set
never grows, the pairs only redistribute weight inside it, and that
redistribution costs ~2 points at k=5 and k=10. Price: concepts 42,094 →
548,645 (13x), mentions 607k → 1.65M, ingest 99s → 242s.

The identity was the best of four measured variants (contiguous trigram →
stemmed → alphabetized → skip-pair within a window of 4; hapax 88.9% → 81.6%
on this corpus). Making the key better did not make the layer useful, because
the ceiling was never the key — it was that composition adds no reachability
over its own components. Left behind the default-off flag.

**Caveat.** `recall` and `recall-fuse` scored 0.000 in both arms: they need the
daemon up for the dense embedder and this run was daemon-less. Equal across
arms, so the comparison stands, but `recall-fuse` is genuinely phrase-sensitive
(it fuses dense with the same `content_rank` BM25) and remains unmeasured.

The base arm reproduced the published numbers (scan MRR 0.240 vs 0.241;
context hit@20 0.422 vs 0.433), which is what validates the build.

## Concept-path expansion + salience: three changes, none shipped (2026-09-03)

All measured on the same store, `scan-nocontent` isolating the concept path
because the content bundle carries ~75% of the full surface and masks it.

### Lift-scored association (`--rank assoc`)

`assoc.py` scores expansion candidates by how SURPRISING their overlap with
the prompt's documents is — `(co/|A|)/(df/N)` — instead of by PPR's diffused
mass. The reasoning: PPR already reaches the co-occurrence neighborhood, so
what is missing is specificity, and under a hard `max_concepts` cap the five
concepts that win the cap ARE the product.

| arm | MRR | hit@20 |
|---|---:|---:|
| scan-nocontent (ppr) | **0.069** | **0.267** |
| scan-assoc-nocontent | 0.007 | 0.044 |

Six to ten times worse. Rejected. The qualitative failure is legible: for
"vacuum under my bed ... old sneakers", the top associations are wedding
vendors (`weddingwire`, `bouquets`, `florists`), because the anchor is built
from whatever `match_concepts` returned and on prose that is function words.

Three sub-findings worth keeping, each a trap the first implementation fell in:
seeds scored `inf` sort ahead of every association and eat the whole cap;
support as a MULTIPLIER on lift re-elects the hubs (when the anchor is loose
every lift sits near 1.0 and the multiplier alone decides); and the union of
all seeds' documents is not "the prompt's documents" — it was 38% of the
corpus, which makes `co/|A| == df/N` and collapses lift to 1.0 for everything.

### Modal salience by corpus type

`_salience` is `central + 1.5*idf + shape + ns_bonus`, where `central`
(PageRank) spans 0..2.5 and `1.5*idf` spans ~0.45. Centrality outweighs
specificity tenfold, so salience RISES with df — on prose it selects function
words. Measured: `sneakers` df=22 scores 1.43, `there` df=864 scores 2.65.

`Store.code_fraction()` separates the regimes unambiguously (refmatrix 0.95,
this corpus 0.004), and blending the weights by it fixes the SELECTION
completely — prose mode picks `sneakers, vacuum, bed, items, stored, spot`
where the default picks `first, items, still, know, need, there`.

It does not fix RETRIEVAL. The 2x2 against the punctuation flag below:

| scan-nocontent | strip ON | strip OFF |
|---|---|---|
| code mode | 0.052 / 0.222 | **0.069 / 0.267** |
| prose mode | 0.059 / 0.267 | 0.062 / 0.267 |

Read the strip-OFF column — against the shipped tokenizer, prose weighting is
WORSE (0.069 -> 0.062). The +13%/+20% it appears to win in the strip-ON column
is not signal; it is prose weighting partially offsetting the other flag's
loss. Judging it on that column alone would have shipped a regression.

### Sentence-final punctuation

`_IDENT_RE` keeps a trailing `.` so `os.path` survives, so the last word of
every prose sentence arrives as `first.` — which `_token_shape_score` reads as
a dotted attribute path and rewards with 1.0, ALSO exempting it from the
shape-0 floor (that gate only fires at shape exactly 0). A bug by inspection.
Removing it cost recall: 0.069 -> 0.052 MRR, 0.267 -> 0.222 hit@20. Sentence-
final position apparently correlates with the topical noun by more than the
noise it admits.

### Disposition

The best of the four cells is the configuration that already ships. All three
land default-off behind `RMX_SCAN_MODE`, `RMX_SCAN_STRIP_PUNCT`, and
`--rank assoc`, with the numbers in their docstrings.

The structural reason all three underperformed: they target the concept path,
which is 0.069 of a 0.241 surface. The content bundle already applies true
BM25 idf, which is the same correction two of these were reaching for.

## tf normalization: a real scaling law that BM25 already absorbs (2026-09-03)

`mentions.weight` is the one intermediate every symbolic surface reads —
`content_rank` BM25 (as tf AND, summed, as doclen), the per-concept bundles,
`build_adjacency` -> pagerank -> `_salience`, `concept_df`, the bitmap
projections. It is also a column with mixed units: `ingest_gmd` writes 2.0 for
a title token and 3.0 for an alias (importance) alongside `float(tf)` for a
body term (frequency), and NULL for a tag. A NULL scores `tf = 0.0` in BM25
while still counting in `concept_df`, so a tag edge is a pure ranking penalty.

The term-frequency distribution is a clean power law on both corpora, with a
CORPUS-DEPENDENT exponent:

| corpus | alpha | R^2 | P(TF>=2) | P(TF>=3) | P(TF>=10) |
|---|---:|---:|---:|---:|---:|
| memaware (prose) | 2.68 | 0.980 | 0.453 | 0.256 | 0.036 |
| refmatrix (code) | 3.53 | 0.981 | 0.163 | 0.035 | 0.001 |

`tf=3` is the top 26% of prose edges and the top 3.5% of code edges, so the
same count carries different information per corpus. For a power law the tail
gives `-log P(TF>=tf) = (alpha-1)*log(tf)`: log-shaped tf with a per-corpus
coefficient. Tested as `RMX_TF_NORM=surprisal` (tabulated empirical tail, not
the fitted exponent) against `RMX_TF_NORM=log` as a control.

| arm | context MRR / hit@20 | scan MRR / hit@20 |
|---|---|---|
| raw (shipped) | **0.160 / 0.433** | **0.241** / 0.411 |
| log | 0.154 / 0.411 | 0.238 / 0.422 |
| surprisal | 0.155 / 0.411 | 0.238 / 0.422 |

**Surprisal and log are indistinguishable** (identical to three decimals on
scan), so the corpus calibration bought nothing over plain compression — the
control is the only reason that is knowable. Both lose to raw on `context`,
the near-pure content_rank surface.

BM25's `k1` saturation is already a tf compressor; stacking a log or a
surprisal transform on top double-saturates. The information-theoretic and the
engineering answers converge, which is the textbook argument for BM25's
saturation reached from the other side.

Untested: code, where alpha deviates furthest from what a fixed `k1` assumes,
and where the calibration therefore has the most room to matter. Also note
`doclen` stays the raw summed weight under all arms — document length is a
property of the document, but the asymmetry could confound.

## Eight discarded signals: one wins, and the ceiling is recall (2026-09-03)

Everything a HUMAN asserts about a document contributed nothing to its score,
while everything an extractor counts drove the whole ranking. Tags scored
literally 0.0 in BM25 (`float(w or 0.0)`) while still counting in `concept_df`,
so a tag DEPRESSED its own concept's idf. Heading depth was parsed into entity
meta and never read. `protected` gated vacuum, never ranking. `rel:` edges drove
graph walks, never term scoring. `RMX_REINFORCE_ALPHA` defaulted to 0.0 and
`apply_to_concept_scores` had no callers at all.

All eight given a path to strength via two mechanisms — term-level boosts
(`boost * idf`, deliberately OUTSIDE BM25 saturation and outside doclen) and
document-level priors (multiplicative). Then measured on TWO corpora, because
MemAware alone cannot see five of them: it is synthetic prose with 0 `rel:`
edges, nothing protected, and 99.6% of nodes at heading level 1.

### The one that won: lead position

Held-out (90 questions disjoint from the weight tuning), `context`:
MRR 0.206 -> 0.248 (+20%), hit@20 0.378 -> 0.511 (+35%), hit@1 +28%. Replicates
the tuning set's +21% across a weight plateau of 0.25..2.0, degrading only past
4.0. Shipped ON (`RMX_LEAD_TERMS`, `RMX_BOOST_LEAD=0.5`); needs re-ingest.

### The rest, on cliquedb — a corpus that HAS the signals

34.8k typed edges, four populated heading levels, 8.6k tag edges, 54 protected.
Known-item retrieval, 400 queries sampled from NON-LEAD BODY lines so the task
cannot flatter the signals under test. PAIRED per-query, because a mean over
400 queries dilutes an effect that touches twelve of them:

| signal | changed | better | worse | net |
|---|---|---|---|---|
| depth=1.0 | 12/400 | 7 | 5 | +2 |
| rel=0.5 | 5/400 | 3 | 2 | +1 |
| tags | 1/400 | 0 | 1 | -1 |
| protected | 0/400 | 0 | 0 | 0 |

Seven better against five worse is a coin flip. The signals are present, the
priors demonstrably move scores (see `tests/test_structural_signal.py`), and
retrieval does not improve.

### Why: the ceiling is recall, not ranking

cliquedb baseline is hit@1 0.447 against hit@20 0.537. **46% of known-item
queries never retrieve the gold document at all**, and most of the 54% that do
are already at rank 1. The band a reordering prior can act on is a few percent
of queries wide, which is exactly the 1-3% each prior touches.

Same wall the phrase layer hit from the opposite side: a phrase cannot reach a
document its component words missed; a prior cannot reach one BM25 missed.
`lead` is the only one of the eight that changes WHICH documents are retrieved
rather than how the retrieved set is ordered, and it is the only one that paid.

## What has NOT been run

Layer B — upstream's continuity-accuracy harness — has never executed. It needs
an answer model and a judge; no Fireworks key, and the OpenAI key returns `429
You have no credits remaining`. `lib/llm.mjs` now routes `claude-*` to the
Anthropic Messages API, so one `ANTHROPIC_API_KEY` unblocks it. Run
`tools/smoke_judge.mjs` first.
