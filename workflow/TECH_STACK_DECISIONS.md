---
gmd: "0.1"
id: TECH_STACK_DECISIONS
title: "Tech Stack Decisions"
tags: [reference]
metadata:
  node_type: doc
---

# Tech Stack Decisions {#root}

Approved libraries and the rationale for each. A dependency not listed here has not been
vetted — propose it (with rationale + alternatives considered) before adding it.

## Approved Libraries {#approved-libraries}

| Library | Purpose | Rationale | Approved |
|---------|---------|-----------|----------|
| duckdb ≥1.5.3 | catalog | embedded, columnar, single-writer semantics fit the daemon model | 2026-05 |
| pylance | vectors | Lance datasets for ANN alongside DuckDB | 2026-05 |
| pyroaring | linkage cells | roaring bitmaps of entity ids per (linkage, concept) | 2026-04 |
| click + rich | CLI | command tree + tables | 2026-04 |
| sentence-transformers | embed/rerank | bge-small + cross-encoder, out-of-process workers | 2026-06 |
| watchdog | file watcher | daemon-owned FS observer | 2026-05 |
| fastapi + uvicorn | hub UI | web control plane on :7777 | 2026-06 |
| pytest + httpx | tests | dev extra | — |

## Rejected / Deferred {#rejected-deferred}

| Library | Considered For | Why Not | Date |
|---------|----------------|---------|------|
| LatticeDB | 4th retrieval condition | BM25 scores all 0.0 on our corpus | 2026-08 |

## Standards {#standards}

- Python 3.14 on the workstation (`>=3.10` declared) · ~100 columns · no formatter/type gate wired
- New dependency = row here first, with alternatives considered
