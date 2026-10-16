---
gmd: "0.1"
id: plan18-catalog-measure-20261015
title: "Plan-18 task 18.1 fleet catalog measurement 20261015"
tags: [plan-18, duckdb, catalog, measurement]
---

# Task 18.1 fleet catalog measurement 20261015 {#root}

rel: implements -> [[task-18.1-catalog-measurement]]

## Per store {#stores}

| store | file MiB | rewrite MiB | reclaimable MiB | f | r | A | B | median s | max s | C | gate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cliquet | 71.3 | 29.8 | 41.5 | 0.256 | 0.582 | A0 | B-disagree | 0.284 | 0.296 | C0 | pass |
| cliquedb | 230.5 | 99.8 | 130.8 | 0.154 | 0.567 | A2 | B-disagree | 1.05 | 1.055 | C0 | pass |
| refmatrix | 789.0 | 176.8 | 612.2 | 0.147 | 0.776 | A2 | B-disagree | 1.938 | 1.98 | C0 | pass |
| viascope | 291.5 | 158.3 | 133.2 | 0.200 | 0.457 | A1 | B-disagree | 1.737 | 1.756 | C0 | pass |
| orderly | 21.8 | 11.8 | 10.0 | 0.345 | 0.460 | A0 | B-disagree | 0.064 | 0.065 | C0 | pass |
| thiquet | 2.8 | 2.0 | 0.8 | 0.550 | 0.272 | A0 | B-disagree | 0.006 | 0.008 | C0 | pass |
| tholley | 241.8 | 34.0 | 207.8 | 0.202 | 0.859 | A2 | B-disagree | 0.424 | 0.471 | C0 | pass |
| atldb | 31.3 | 16.5 | 14.8 | 0.352 | 0.472 | A0 | B-disagree | 0.134 | 0.143 | C0 | pass |

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
