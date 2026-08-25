# MemAware — proactive-retrieval benchmark for rmx

[MemAware](https://github.com/kevin-hs-sohn/memaware) (Son, 2026) measures
something no other memory benchmark does: whether an agent **surfaces relevant
past context nobody asked for**. LoCoMo, LongMemEval and MemoryAgentBench all
hand the system a query and grade the lookup. MemAware hands it a task request
in which the relevant history is deliberately *unmentioned*, and grades whether
the system volunteers it.

That is the surface refmatrix ships. `rmx scan-prompt` runs on every
UserPromptSubmit and injects a graph neighbourhood the user never requested;
`memory compile` builds the standing subject overview. CSN measures the
symbolic retrieval floor — the thing rmx already beats CodeRankEmbed on
(0.972 vs 0.959 MRR@10). It says nothing about proactive surfacing. This fills
that hole.

## Why the baselines are so low, and why that matters

| Method | Easy | Medium | Hard | Overall | median tokens |
|---|---:|---:|---:|---:|---:|
| No memory | 1.0% | 0.7% | 0.7% | **0.8%** | 0.6–1.1k |
| BM25 search | 4.7% | 1.7% | 2.0% | **2.8%** | ~4.5k |
| BM25 + vector | 6.0% | 3.7% | 0.7% | **3.4%** | ~1.7k |

Published baselines, 900 questions, answer model Kimi K2.5, judge GPT-5.1.

Nobody is above 3.4%, and searching costs 5× the tokens of not searching to buy
two points. The hard tier — where the request and the memory share no keywords
at all ("Ford Mustang air filter" → "user redeems coupons at Target") — is
unsolved by every search-based approach; BM25+vector scores 0.7% there, exactly
the no-memory floor. Upstream's stated conclusion is that this needs "a holistic
view of the user's history", not a better retriever.

A floor that low is a double-edged thing to wire up. It means there is enormous
headroom, and it also means **the metric is barely off zero**, so a subset run
of 90 questions distinguishes 2% from 4% only very noisily. Read the caveats
below before quoting any number this harness produces.

## Layer A / Layer B

The upstream harness spends two LLM calls per question (answer + judge) and
grades *continuity accuracy* — did the answer visibly use the past context.
That conflates two different failures: the retriever never surfaced the
session, or it did and the answer model ignored it.

Every question names its `answer_session_ids`, and `prepare.py` splits the
corpus one file per session, so the first half of that is recoverable as a
plain document-retrieval metric:

- **Layer A — `retrieval_eval.py`.** Recall@k / MRR of the correct session.
  Deterministic, zero API cost, seconds to run. *Run this first.* If Recall@20
  is at the floor there is nothing for Layer B to find and a paid run is wasted.
- **Layer B — `run.sh`.** The upstream harness verbatim, with rmx wired in as
  conditions. Produces the number comparable to the table above.

## Setup

Layer B needs credentials Layer A does not. Upstream wants `OPENAI_API_KEY`
(judge) and `FIREWORKS_API_KEY` (Kimi answer model); on this machine neither
is usable — no Fireworks key, and the OpenAI key returns `429 You have no
credits remaining`. So `lib/llm.mjs` here is a vendored copy of upstream's
that adds **Anthropic as a third provider**: any model id beginning with
`claude-` routes to the Messages API, and one `ANTHROPIC_API_KEY` can then
drive the judge, the answer model, or both.

```bash
export ANTHROPIC_API_KEY=...
MEMAWARE_JUDGE=claude-sonnet-5 node tools/smoke_judge.mjs   # do this FIRST
MEMAWARE_JUDGE=claude-sonnet-5 MEMAWARE_MODEL=claude-sonnet-5 ./run.sh rmx-scan
```

`tools/smoke_judge.mjs` is two calls, and it exists because run.mjs hard-codes
the judge at `maxTokens: 20`. A model that spends that budget before emitting
text parses as NO and scores *every* answer 0 — a full run would complete,
look plausible, and be worthless. Check before spending.

Swapping either model makes the run incomparable to the published table until
`no-memory` and `bm25-search` are re-run under the same pair. Budget for that:
four conditions × 900 questions × 2 calls.

```bash
python3 prepare.py --clone      # fetch upstream, split 91 days -> 1307 sessions
python3 ingest.py               # build a dedicated rmx store over the corpus
node tools/bm25_rank.mjs --questions subsets/stratified-30.json
python3 retrieval_eval.py       # Layer A — free
./run.sh rmx-scan               # Layer B — costs API calls
```

## What prepare.py has to fix

1. **Split.** Upstream ships 91 *daily* files, each concatenating ~14 sessions
   — one is up to 858KB. That is a poor BM25 document and a worse graph node,
   and it is part of why the published BM25 baseline does so badly. Every
   session carries a `## Session <id>` header and the mapping accounts for all
   1307, so the split is exact. Both rmx and the re-run BM25 baseline get the
   same granularity, so a comparison measures retrieval and not chunk size.
2. **Relocate.** `_mapping.json` holds the author's absolute paths and
   `run.mjs` feeds absolute paths straight to `existsSync` — on any other
   machine the index comes back empty *without erroring*.
3. **Reshape as GMD.** This one is a finding, not plumbing: rmx's general
   markdown pass extracts only *structured* signals (bold metadata, ADR refs,
   concept-doc linkages, fenced specs). Measured on the raw corpus: **1309 doc
   entities, 0 `mentions` rows, 3 concepts.** Plain prose produces no graph at
   all, so every symbolic surface degrades to the grep backstop. `ingest_gmd`
   is the pass that runs the body term-frequency sweep, so the sessions are
   emitted with GMD frontmatter and ingested `--as-memory` — which is also the
   honest analogy, since in rmx a past session *is* a memory.
4. **Stratify.** `run.mjs --limit N` takes the first N in file order and file
   order is not tier-balanced, so a limited run silently over-weights whichever
   tier leads. Use `subsets/`.

## Reproducibility traps in the upstream harness

- **Provider seam.** The judge is constructed inside `run.mjs`, which imports
  `./lib/llm.mjs` directly — a condition cannot inject a provider. `run.sh`
  therefore *copies* (never symlinks — Node resolves bare imports from a
  module's real path) our `lib/llm.mjs` over the clone's, keeping the original
  as `llm.upstream.mjs` and warning if its sha has drifted from what we
  vendored against.
- **Judge mismatch.** `results/baselines.json` records `"judgeModel":
  "gpt-5.1"`, but `lib/llm.mjs` defaults `MODELS.JUDGE` to
  `gpt-4o-mini-2024-07-18`. Numbers produced at the default are not comparable
  to the published table. `run.sh` sets `MEMAWARE_JUDGE=gpt-5.1`.
- **Judge output budget (suspected, NOT verified).** `judgeResponse` caps the
  judge at `maxTokens: 20`. That is fine for a non-reasoning model; on a
  reasoning judge the budget can plausibly be consumed before any visible
  token is emitted, and `parts[0]` would then parse to a 0. This has *not*
  been confirmed here — the attempt returned `429 You have no credits
  remaining` for both `gpt-5.1` and `gpt-4o-mini`. Check it on a handful of
  questions before trusting a full run.
- **Answer-model substitution.** Upstream answers with Kimi K2.5 via Fireworks.
  Substituting another model invalidates comparison against the published
  table — the no-memory and bm25-search baselines must be re-run under the
  same substitution.
- **Token accounting.** `tokens_used` is a delta of a shared global counter
  taken around `evaluate()`. The run loop is sequential, so this is sound as
  written, but it would silently misattribute under any concurrent evaluate.

## Honest expectations for rmx

- The corpus is one synthetic person's chat history. There are **no structural
  edges** in it — no calls, defines, imports. The part of the graph that wins
  CSN is simply absent, and rmx is reduced to its associative layer
  (`mentions` TF, co-occurrence, PPR over those). Expect the CSN result to
  carry over not at all.
- The hard tier asks for an inference ("Target sells car parts *and* the user
  has a coupon relationship there"), not a link. A co-mention walk reaches it
  only if some past session put the two in the same room. Where the corpus
  never did, no graph can.
- `scan-prompt`'s ranking was tuned against code-and-notes prompts, with a
  stoplist and a junk-token gate built for that register. Conversational prose
  is a different distribution.

The interesting question is not whether rmx clears 3.4% — it is whether the
graph beats its own dense control (`rmx-recall`) on medium and hard. That
difference is what the whole conceptual-memory thesis predicts, and it is
measurable here for the first time.
