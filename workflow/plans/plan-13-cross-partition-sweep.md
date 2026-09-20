---
gmd: "0.1"
id: plan-13-cross-partition-sweep
title: "Union the project's own partitions: does reaching sessions + memory + code in one sweep change the reachable set?"
tags: [plan, retrieval, fusion, partitions, sessions, memaware]
metadata:
  node_type: plan
  status: drafting
  created: 2026-09-20
  revised: 2026-09-20
  audit: bsd-plan13-cross-partition-sweep-0cb8b1a
---

# Proposed Plan: a cross-partition fusion sweep {#root}

**Date:** 2026-09-20 (revised same day after `@ch-bsd` returned DIRTY, 12 findings)
**Status:** Drafting
**Location:** `workflow/plans/plan-13-cross-partition-sweep.md` — permanent home; stage is
`metadata.status`.

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: derives-from -> [[bsd-plan13-cross-partition-sweep-0cb8b1a]]
rel: derives-from -> [[project_memaware_benchmark]]
rel: derives-from -> [[project_structural_signal_lead_wins]]
rel: amends -> [[0001-intuition-lance-integration]]
rel: reinforces -> [[feedback_measure_the_path_users_run]]
rel: reinforces -> [[feedback_read_identifiers_at_write_time]]
rel: reinforces -> [[project_verbs_layer_antidrift]]
rel: contradicts -> [[project_retrieval_negatives_2026_09]]

## What the first draft got wrong {#revision}

The first draft was audited before any code was written and came back **DIRTY — 5 BULLSHIT**. The
corrections are load-bearing enough to lead with, because three of them change what this plan is:
{#revision-lead}

1. **The arbiter could not see the mechanism.** The MemAware store is ONE partition
   (`eval/memaware/paths.py:44` pins `PARTITION = "memaware"`; the whole corpus enters via
   `ingest-gmd --as-memory`). Three of four proposed legs are empty there by construction, so the
   pre-registered criterion could neither pass by the claimed mechanism nor fail informatively.
2. **The motivating number was the pre-fix row.** `scan-prompt` is **0.378 hit@20 / 0.241 MRR@20**
   today (`eval/memaware/REPORT.md:21,34`, `docs/PERFORMANCE.md:286-289`), not 0.200/0.043. That row
   is labelled "starting point" in the source. The live gap to bm25 is **0.066 hit@20 and MRR
   parity**, not a 2.2x deficit.
3. **The session leg already ships.** `src/refmatrix/session_ingest.py` (295 lines) writes
   turn-level prompt and decision cards into a `sessions-<project>` partition, with
   `rmx session recall|show|list|stats` over it. What stands between `rmx context` and a session
   answer is a default-false boolean: `context.py:346`
   `if not include_sessions and _is_session_card(ent.name): continue`.

Also corrected below: the PASS bar was already cleared by `rmx context` ([[#acceptance]]), the
dedupe rationale did not match `fuse_rrf` ([[#dedupe]]), the CSN secondary measured a path the
change cannot reach ([[#acceptance]]), and "rank, never score" contradicted a recorded negative
([[#principle-rank]]).

## Context {#context}

No surface unions **the project's own partitions**. `rmx context` reads the project code/doc
partition; `rmx memory recall` reads the memory partition; `rmx session recall` reads
`sessions-<project>`; `scan-prompt` composes over what those return. One union does ship —
`verbs.memory_recall(scope="both")` fans out to the hub's global store and merges with
`verbs.merge_scope` (`verbs.py:375-399`) — but it crosses a STORE boundary, not a partition one,
and it is the only one. {#context-lead}

The live Layer A standings (90 questions, deterministic, `eval/memaware/REPORT.md`):

| surface | hit@20 | MRR@20 |
|---|---:|---:|
| **`rmx context` (+lead)** | **0.511** | **0.248** |
| bm25-per-session (upstream reference) | 0.444 | 0.242 |
| `rmx memory recall` +rerank (0.42.0) | 0.422 | 0.218 |
| `rmx memory recall` (dense) | 0.378 | 0.180 |
| `rmx scan-prompt` | 0.378 | 0.149 → **0.241** re-measured (`PERFORMANCE.md:289`) |
| `rmx memory recall --fuse` | 0.378 | 0.180 |
| bm25-per-day | 0.156 | 0.058 |

rmx is no longer behind on this benchmark: `rmx context` leads it. So the motivation is NOT "our
surfaces are weak". It is narrower and checkable: **every one of those numbers was produced by a
retriever searching one partition, and the product's answers are spread across four.** {#context-numbers}

### Why this and not another reranking prior {#why-this}

[[project_structural_signal_lead_wins]] measured eight discarded signals and closed with a rule:
ask whether an idea changes the candidate SET or reorders the found one. Seven only reordered and
none paid; `lead` changed which documents were retrieved and is the one that shipped.
`docs/PERFORMANCE.md#memaware-ceiling` holds that the remaining ceiling is recall, not ranking
(known-item hit@1 on a healthy store is **0.808** post-re-derive — the 0.447 "ceiling" was pool
contamination and is retracted at its source). A union across partitions changes the reachable set
by construction. That is the whole claim, and [[#gate-0]] is designed to kill it cheaply if it is
wrong. {#why-this-lead}

## Proposed Approach {#proposed-approach}

### Measure before building {#measure-first}

**13.0 is the plan.** Everything after it is contingent. The measurement needs NO new code: the
Layer A harness, pointed at a store that actually has two populated partitions — this repo's own
store plus `sessions-refmatrix` — with `rmx context --include-sessions` and `rmx session recall`
as conditions against `rmx context` as control. If reaching the session partition does not move
hit@20 on a question set whose answers live there, the plan closes for the price of one report.
{#measure-first-lead}

### One principle, if 13.0 says go {#principle}

**Generate candidates per partition, fuse, dedupe by identity.** No new scorer, no new index, no
new ranking prior. Each leg is a call that exists; the sweep is the union around them.

- `recall.hybrid_recall` (`recall.py:64`) / `recall.hybrid_memory_recall` (`recall.py:120`) fuse
  dense ⊕ symbolic INSIDE one partition; the caller binds the partition.
- `query.fuse_rrf(ranked_lists, k=60)` (`query.py:33`) fuses ranked id lists.
- `Store.with_partition(name)` (`store.py:1590`) is how one Store addresses a second partition —
  and its docstring carries the constraint: *not safe under concurrent ops on the same Store; wrap
  with `d._store_lock` at the daemon op layer*. See [[#cost]].
- `verbs.merge_scope` (`verbs.py:375-399`) already dedupes a two-source union by name with a
  round-robin that guarantees the smaller source representation. It is 13.2's ancestor.

### Fusion: the recorded negative applies, and this is how it is escaped {#principle-rank}

RRF is a **measured negative as a default** in this repo, on both of this plan's corpora, and the
first draft re-proposed it without engaging: `docs/PERFORMANCE.md#negatives` (dense 0.848 vs fused
0.794 MRR@10 — `--fuse` stays opt-in), `project_rrf_landed` (BM25 score-summation 0.97 vs RRF 0.28
on csn_python), and `eval/memaware/REPORT.md:64-67` (`--fuse` identical at this scale, differing on
1 question of 90). {#principle-rank-lead}

The honest argument is narrower than "rank, never score": **within** a partition, per-linkage scores
share term statistics and summing them is measurably better; **across** partitions they do not, so
order is the only comparable quantity. That claim is testable and therefore pre-registered as two
arms rather than asserted in prose:

- **arm R** — RRF over per-leg ranks
- **arm S** — score-summed after per-leg min-max normalisation

Both run in 13.5. Whichever wins ships; if S wins, `#principle` is amended and the negative stands
un-re-derived.

### The legs {#legs}

| leg | partition | candidate generation | exists? |
|---|---|---|---|
| project | project code+doc | `content_rank` ⊕ dense, as `build_context` does | yes |
| memory | `memory-<project>` | `hybrid_memory_recall` | yes |
| session | `sessions-<project>` | `hybrid_memory_recall` on that partition | **partition ships; no unioned reader** |

**Three legs, not four.** The first draft split the project partition into "code" and "docs" legs.
They are ONE partition, so two legs drawing the same pool can return the same entity id — and RRF
sums per id, inflating an entity because of an arbitrary split. Dropped. {#legs-lead}

Each leg is capped independently so a 60k-row partition cannot crowd out a 200-row one before
fusion sees either. Cap defaults are an output of 13.5, not an input.

### Dedupe is slot-crowding, not rank inflation {#dedupe}

The first draft claimed RRF would sum three copies of one answer into a false winner. It would not:
`query.py:45-49` sums per `entities.id`, and ids are store-global with
`UNIQUE(partition_id, kind, name)` — the same decision written as a session card, a memory and an
ADR is three DIFFERENT ids that tie rather than compound. The real harm is **crowding**: three of
twenty slots spent on one answer. The fix is the same (collapse to canonical identity before
fusion, keep the best-ranked instance, record the rest as provenance) and `merge_scope` is the
precedent. {#dedupe-lead}

**Where summation genuinely bites:** two legs over one partition (now dropped), and any future leg
that re-enters the same pool.

### Cross-store fusion is out of scope, and why {#cross-store}

`entities.id` is unique within a ROOT and collides across roots. `fuse_rrf` over ids is therefore
safe across partitions of one store and **silently wrong** across the project/global boundary that
`memory_recall(scope="both")` crosses. This plan unions partitions of ONE store. Any later global
leg must fuse on `(root, id)`, and that is a separate decision. {#cross-store-lead}

## Prior art this plan must not pretend away {#prior-art}

`docs/adr/0001-intuition-lance-integration.md:114-115,160` already specified "cross-partition fusion
uses the existing `partition_fuse` infrastructure" and listed "cross-partition fuse defaults on for
`rmx memory recall`" as a Phase B deliverable. **`partition_fuse` appears nowhere in `src/`** and
that ADR is still `Status: Proposed` (2026-05-27). `project_partitions_canon` names the same gap:
"needs a query engine that can open additional Stores keyed by partition_id" — which is what
`with_partition` became. This plan is that clause, built and measured, five months later.
{#prior-art-lead}

## Acceptance {#acceptance}

Pre-registered before the code exists, per [[project_helix_phase2_decision_criterion]]'s discipline.
{#acceptance-lead}

### Gate 0 — the kill shot (task 13.0, no new code) {#gate-0}

Layer A protocol on a **two-partition store**: this repo's store + `sessions-refmatrix`, question
set per [[#question-set]]. Conditions: `rmx context` (control), `rmx context --include-sessions`,
`rmx session recall`, and the oracle union (the set-union of the first and third, scored as one
list — the sweep's ceiling without building it).

- **GO** — the oracle union beats the best single condition by ≥ 0.05 absolute hit@20. There is
  reachable set to win and a sweep can win it.
- **STOP** — it does not. Record the negative beside the phrase layer and the eight signals; close
  the plan. **This is a real outcome and costs one report.**

### Gate 1 — the build pays (task 13.5, only if GO) {#gate-1}

Primary arbiter is the SAME two-partition store and question set, because it is the only one where
the mechanism can fire.

- **PASS** — sweep hit@20 ≥ (best single condition from 13.0) **+ 0.05 absolute**, and MRR@20 not
  below that condition's. The bar is derived from 13.0's measured control, never from a number
  quoted in prose.
- **PARTIAL** — gain positive but under 0.05: ship behind a flag, record the delta, do NOT adopt
  into `scan-prompt`.
- **FAIL** — no gain over the control: close, record.

**Attribution arms (both required, else a PASS is unattributable):**

- `--no-rerank` — the memory leg inherits the cross-encoder that `scan-prompt` and `context` do NOT
  run (`REPORT.md:202-203`). Without this arm a gain is attributable to rerank, not to the union.
- arm R vs arm S ([[#principle-rank]]).

### Secondary — no regression, stated as a test not an eval {#secondary}

The first draft defended CSN MRR@10 0.961 through `eval/production/csn_code.py`. That harness ranks
in-process (`csn_code.py:158`, `s.content_rank(terms, kinds=["code"], limit=…)`) — one Store, one
partition, no CLI, no verb — so a new `sweep` verb cannot change its result and the criterion would
pass unconditionally. It is replaced by an assertion that can fail: **`content_rank` and
`build_context`'s default path are byte-identical before and after** (a test, not a two-hour eval),
plus `rmx context` without `--include-sessions` returning the same ranked ids on a fixture store.
{#secondary-lead}

### Diagnostic — per-leg contribution {#acceptance-diag}

For each question, which leg produced the winning candidate. **This requires harness work**, which
is in 13.5's scope: `eval/memaware/retrieval_eval.py:75-111` (`_ids()`) keeps the first id-looking
string per record and returns a flat `list[str]`, so a `leg` field on the sweep's output is walked
past and dropped. The method contract and `score()` both change, or a sidecar leg map is written.
A sweep that "wins" with 95% of winners from one leg is that leg with extra latency, and the report
must be able to say so.

## The question set {#question-set}

13.0 needs questions whose answers are known and whose gold documents live in DIFFERENT partitions.
MemAware's cannot serve: its corpus is one partition. Source, in preference order:

1. **Known-item from this repo's own history** — a prompt from a past session (`sessions-refmatrix`)
   whose answer is a memory or an ADR. `.refmatrix/query.log` `kind="scan"` bodies are real prompts
   (`eval/memory_recall/mine_queries.py` already mines exactly these), and `helix.log` records what
   was retrieved for them.
2. **Cross-partition pairs already in the graph** — a `rel:` edge whose endpoints sit in different
   partitions is a labelled positive.

Both are pooled + judged TREC-style, as `eval/memory_recall/` does. **Task 13.0 owns building this
set and it is the plan's first real cost.** A set of ≤ 60 questions is enough to see a 0.05 effect
and is what the existing judged harness already handles. {#question-set-lead}

## Cost budget {#cost}

`scan-prompt` fires on every prompt, and three constraints the first draft missed are load-bearing:
{#cost-lead}

1. **The lock-free read path cannot serve a second partition.** `search.cached_replica(root)`
   (`search.py:38-55`) opens `Store(root, partition=discovery.store_name(root), read_only=True)` —
   cached per root, one partition, fixed. Every non-default leg is a DAEMON OP.
2. **Daemon ops serialize on `_store_lock`**, because `with_partition` is not concurrency-safe on
   one Store. The sweep's wall clock is the SUM of its legs, not the max — the shape already filed
   twice ([[bsd-impressions#imp-fleet-sum-timeouts]]).
3. **`daemon.call` defaults to `retries=2`**, tripling any per-leg timeout
   ([[feedback_daemon_call_retries_multiply_timeouts]], the 30 s grep wall).

So: ONE deadline for the sweep, `retries=0` on every leg RPC, legs that miss the deadline DROPPED
and COUNTED (never silently awaited), and the p95 measured on the hook path before any adoption.
Adoption into `scan-prompt` is its own task, gated on the measured p95 and on Gate 1 reading PASS.

## Risks {#risks}

- **13.0 says STOP.** Most likely outcome, and the cheapest one. Budgeted for.
- **The session partition is stale on the measuring store.** Session ingest is scheduled
  (`session_launchctl.py`); a store whose sessions lag makes the union look worse than it is. 13.0
  verifies freshness before measuring and reports the lag.
- **A leg returns nothing and fusion absorbs it.** Each leg reports its candidate count; a zero is
  an error line, not an empty list ([[feedback_no_silent_failures]]).
- **The sweep becomes a second way to do retrieval.** If it ships, `context`'s cross-partition story
  must be the sweep or must be the filter flag — not both ([[bsd-impressions#imp-two-paths]]).

## Tasks {#tasks}

Specs under `workflow/plans/plan-13-cross-partition-sweep-tasks/` — required before `approved`.

| task | what | gate |
|---|---|---|
| **13.0** | the two-partition question set + the oracle-union measurement, with shipped code only | **GO/STOP** |
| 13.1 | the `sweep` verb: per-leg generation via `with_partition`, one deadline, `retries=0`, per-leg counts | after GO |
| 13.2 | canonical-identity dedupe before fusion, provenance for collapsed copies, modelled on `merge_scope` | after 13.1 |
| 13.3 | CLI + MCP adapters and the verb-parity test | after 13.1 |
| 13.4 | `include_sessions` policy: which surfaces default it true, decided on 13.0's numbers | after GO |
| 13.5 | measurement: Gate 1, both attribution arms, the per-leg diagnostic INCLUDING the harness change | **PASS/PARTIAL/FAIL** |
| 13.6 | `scan-prompt` adoption, gated on measured p95 and on Gate 1 PASS | after PASS |

## Open questions {#open}

1. **Does `scan-prompt` adopt the sweep or call it?** 13.6 decides on the measured p95.
2. **Default-on or flag?** This project ships a retrieval change default-on only with a held-out
   replication ([[project_structural_signal_lead_wins]]).
3. **Is `include_sessions` simply the answer?** If 13.0 shows the oracle union pays and the gain is
   carried entirely by the session leg, the cheapest product change is flipping that default for
   `context` — and the sweep is unnecessary. 13.4 must be allowed to reach that conclusion.
   {#open-lead}
