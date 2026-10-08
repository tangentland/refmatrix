---
gmd: "0.1"
id: spike-2026-10-06-loc-coloc
title: "Spike 2026-10-06: lift-gated expansion, proximity and sentence co-location"
tags: [eval, spike, retrieval, helix, co-location]
---

# Spike 2026-10-06 — what ranks known items better than BM25 alone {#root}

Throwaway measurement scripts and their logs from the helix-unification discussion
(ADR-0004). Evidence, not product: nothing here is imported by `src/`. Every script
reads a COPY of a store's read replica (`catalog.read.duckdb` copied to a scratch
`.refmatrix/catalog.duckdb`) — never a live store, never through a daemon.

rel: evidence-for -> [[refmatrix/adr-0004-unified-location-space-index]]

## Result {#result}

**Sentence co-location** — the best weighted coverage of the query's terms inside ONE
sentence of the candidate's full body, `max_sentence Σ w(t) / Σ w(all)` with
`w = idf × burstiness` — added to normalised BM25 at weight ≈2.0, static, no router:

| set | base MRR | + sentence co-location | won/lost |
|---|---|---|---|
| cliquedb `lines` (n=288) | 0.921 | 0.959 | +19/−1 |
| cliquedb `merge` (n=288) | 0.746 | 0.793 | +42/−10 |
| MemAware test-720 (untouched) | 0.185 | 0.211 | +134/−69 |

Paragraph-level co-location is redundant with sentence-level (the split is not
identifiable; tune/test disagree). {#result-table}

## Negatives {#negatives}

- NPMI-admitted query expansion fed back into BM25 (`npmi_expand_eval`): never won a
  query, lost 4–26 of 37 — the PRF shape again.
- Unweighted token MinDist (`prox_rerank_eval`): neutral; token distance worse than
  sentence distance everywhere.
- Confidence gates (`cliq_gate*`/`mem_gate*` logs) and a top-1 margin rule
  (`margin_eval`): no signal beat a plain top1/top2 ratio, and with full bodies the
  router only costs accuracy. Kept only as a latency cascade idea.
- Unbounded same-sentence sums ("sentsum", `*_fullw_eval` logs): length-biased,
  collapses near-verbatim lookups at full weight.

## The artifact that inverted a conclusion {#tldr-artifact}

Until `cliq_grid3`, cliquedb text came from `entities.tldr`, which is TRUNCATED
(median 500 chars, max 1500) while sections run 2.6–31 KB. In all 40 `lines` losses
the gold section scored low or zero co-location because the query line sat past the
cut (`margin_diag.log`, `tldr_diag.log`). Reading each GMD anchor's full section from
its file (`meta.line` to the next heading) turned −40 into +19/−1. Earlier logs that
show a verbatim-vs-spread "conflict" are superseded by `cliq_grid3.log`.

## Running {#running}

```bash
# copy a replica first; scripts take the scratch .refmatrix root as argv[1]
mkdir -p /tmp/clq/.refmatrix && cp ~/github/atollogy/bdep/cliquedb/.refmatrix/catalog.read.duckdb /tmp/clq/.refmatrix/catalog.duckdb
.venv-eval/bin/python eval/spikes/2026-10-06-loc-coloc/cliq_grid3.py /tmp/clq/.refmatrix 2>&1 | tee workflow/review-output/spike-cliq-grid3.log
```

MemAware scripts read `/Volumes/littlebig/memaware` (corpus, qrels, upstream
`questions.json`). `cliq_grid3.py`/`mem_grid2.py` pickle per-query features and
`margin_eval.py` reads those pickles; the pickle paths are hard-coded to the
session scratchpad and must be edited to rerun. `probe1/probe2` logs came from
inline scripts (burstiness, subsumption, NPMI admission eyeball) not saved here. {#running-notes}
