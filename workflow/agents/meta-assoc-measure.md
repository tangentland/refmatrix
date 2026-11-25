---
gmd: "0.1"
id: agent-brief-meta-assoc-measure
title: "Brief: M4, measure seven candidate meta-level associations on existing logs (Q84 = a, L252)"
tags: [agent-brief, measurement, m-lane, retrieval, associations]
metadata:
  node_type: brief
  created: 2026-11-25
---

# M4: candidate meta-level associations, measured before anything is built {#root}

rel: implements -> [[plan-of-plans#questions]]
rel: depends-on -> [[measurement-task-21.5-usage-weight-2026-11-13]]

**Why.** The weights carry ingest structure only. The measured ceiling is RECALL, not ranking
(cliquedb known-item: hit@1 0.447, hit@20 0.537; 46% of queries never retrieve the gold), so an
association earns its place by bridging vocabulary or by a precise cue, not by reordering. The
user chose to measure seven candidates on the logs already on disk before building any (Q84 = a,
2026-11-25). {#why}

## The candidates {#candidates}

1. **Search-resolution bridge** (query → item): a query that missed or returned the wrong thing,
   followed within N events by a Read / Edit / `rmx context` of item F. Control: queries with no
   such follow-up; the follow-up rate for a random item.
2. **Co-change** (file ↔ file, symbol ↔ symbol): changed in the same commit (`git log`).
3. **Error → fix** (normalised error signature → files / bug row): `workflow/bug_registry.md`
   symptoms and the files of the fix commits; tool outputs in the STM ring as cues.
4. **Decision provenance** (file → ruling): commit bodies citing L-rows, Q ids, bug ids.
5. **Staleness** (memory ↔ the code it names, with the sha of last verification): does churn of
   the named files after a memory's `updated:` predict that the memory is later superseded or
   corrected?
6. **Corrections** (delivered item → contradicted): delivered, then superseded, reverted or
   corrected by the user. A demote-only signal: measure its precision as a negative.
7. **Read depth** (cue → anchor): Read offset/limit on large docs: how concentrated are reads on
   a few anchors, and would anchor-level delivery cut payload bytes without losing the read?

{#candidates-list}

## Method {#method}

- **Bands first.** Before reading any result, write in the doc, per candidate: the metric, the
  held-out split (time-ordered: fit on the older part, evaluate on the newer), the control, and
  three or four bands each with an action (build / measure more / drop). Commit that section
  alone first; its sha is the pre-registration.
- **Metric on the product's path.** For the recall candidates (1, 2, 3, 4), the question is: for
  held-out queries or tasks whose gold item the current retrieval MISSED (from
  `recall-events.jsonl` / `query.log` and the later touch), would the association have reached
  the gold? Report reach@k and the false-reach rate, against the control. Reuse the
  `eval/production` harness or MemAware Layer A where they fit
  (`feedback_measure_the_path_users_run`); say when you cannot.
- **Volume.** For each candidate, the evidence count per week at today's activity, so the user
  sees which would have enough data to fit.
- **Known negatives, not re-run:** more graph hops, PRF, term cliques, the phrase layer,
  usage-weighted term scores (`project_retrieval_negatives_2026_09`,
  `project_structural_signal_lead_wins`). Lead position won as its own linkage; a candidate that
  wins is also proposed as its own linkage, never folded into `mentions.weight`.

{#method-list}

## Data and rules {#rules}

- **Read-only on copies.** Copy `.refmatrix/query.log`, `recall-events.jsonl`, `stm/`,
  `sessions/` and `catalog.read.duckdb` of the dev store (and the global store's where needed)
  with `cp -c` into a short `mkdtemp()` root, `chmod a-w`, open DuckDB with `read_only=True`
  under `.venv-eval`, delete the copies at the end. Never open a live store; never `rmx sync`,
  `ingest`, `memory add`, `daemon …` or `hub …`.
- **Nothing raw in the repo** (`feedback_no_raw_prompts_in_public_repo`; the repo is public):
  the doc carries counts, rates, intervals and hashed ids only; no prompt text, no query text, no
  tool output excerpts.
- Work in a littlebig clone `/Volumes/littlebig/refmatrix-m4` on branch `m4-meta-assoc` from
  the dev tree's `master`; write the doc at
  `docs/architecture/explorations/meta-associations.md` (GMD: frontmatter, an anchor on every
  heading, `rel:` edges), scripts under `workflow/measurements/meta-associations-2026-11-25/`.
  Commit there; never touch the dev tree, never push. `./scripts/lint-gmd.sh` zero errors.
- One test-lane process at a time on this machine: the I1.b1 verify lane may still be running;
  keep CPU light, no test suites. Every background wait has a deadline. Never `find /`.
- Name a mechanism only after measuring it (`feedback_causal_story_before_evidence`).
- Report as text (or a file in the clone with its path): the pre-registration sha, the final
  sha, one line per candidate (metric, result with interval, band, action), and what you could
  not measure and why.

{#rules-list}
