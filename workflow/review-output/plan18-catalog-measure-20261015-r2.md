---
gmd: "0.1"
id: plan18-catalog-measure-20261015-r2
title: "Plan-18 task 18.1 fleet catalog measurement 20261015"
tags: [plan-18, duckdb, catalog, measurement]
---

# Task 18.1 fleet catalog measurement 20261015 {#root}

rel: implements -> [[task-18.1-catalog-measurement]]

## Per store {#stores}

| store | file MiB | rewrite MiB | reclaimable MiB | f | r | A | B | median s | max s | C | gate | duckdb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cliquet | 71.3 | 30.0 | 41.2 | 0.256 | 0.579 | A0 | B-disagree | 0.327 | 0.329 | C0 | pass | 1.5.3 |
| cliquedb | 230.5 | 100.5 | 130.0 | 0.154 | 0.564 | A2 | B-disagree | 1.153 | 1.186 | C0 | pass | 1.5.3 |
| refmatrix | 789.5 | 178.3 | 611.2 | 0.138 | 0.774 | A2 | B-disagree | 2.304 | 2.33 | C0 | pass | 1.5.3 |
| viascope | 291.5 | 158.8 | 132.8 | 0.200 | 0.455 | A1 | B-disagree | 1.861 | 1.876 | C0 | pass | 1.5.3 |
| orderly | 21.8 | 11.5 | 10.2 | 0.345 | 0.471 | A0 | B-disagree | 0.063 | 0.064 | C0 | pass | 1.5.3 |
| thiquet | 2.8 | 2.0 | 0.8 | 0.550 | 0.272 | A0 | B-disagree | 0.006 | 0.006 | C0 | pass | 1.5.3 |
| global | 241.8 | 33.8 | 208.0 | 0.202 | 0.860 | A2 | B-disagree | 0.42 | 0.424 | C0 | pass | 1.5.3 |
| atldb | 31.3 | 16.5 | 14.8 | 0.352 | 0.472 | A0 | B-disagree | 0.132 | 0.134 | C0 | pass | 1.5.3 |

## Fleet verdict {#verdict}

- **verdict:** 18.3 goes to the user (lift C12 for an OFFLINE hand-run reclaim)
- **reclaim_candidates:** ['/Users/tholley/github/atollogy/bdep/cliquedb/.refmatrix', '/Users/tholley/claude_tools/refmatrix/.refmatrix', '/Users/tholley/github/atollogy/bdep/viascope/.refmatrix', '/Users/tholley/.refmatrix']
- **helix:** []
- **noisy:** []
- **band_mode:** growth
- **in_daemon_feasible:** True

## Bands (pre-registered, task-18.1 R3) {#bands}

- `min_reclaim_bytes` = 67108864
- `a1_r` = 0.2
- `a2_r` = 0.5
- `b_agree` = 0.1
- `c0_s` = 30.0
- `c1_s` = 120.0
- `noisy_ratio` = 1.5
- `in_daemon_max_s` = 5.0
