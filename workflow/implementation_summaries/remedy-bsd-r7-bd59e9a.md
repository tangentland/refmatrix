---
gmd: "0.1"
id: impl-remedy-bsd-r7-bd59e9a
title: "Remediation of ch-bsd r7 (fa3d7ad..bd59e9a): vector deletes and rerank degrades are said out loud, and a phrase-context rerank that never ran"
tags: [implementation-summary, bsd, remediation, rerank, lance, models]
metadata:
  node_type: summary
  audit: bsd-r1-remedy-r7-bd59e9a
  created: 2026-10-07
---

# Remediation of ch-bsd r7 {#root}

rel: implements -> [[bsd-r1-remedy-r7-bd59e9a]]
rel: amends -> [[impl-remedy-bsd-r6-92c374c]]

Round 7 was DIRTY with 7 findings (0 BULLSHIT, 2 SKETCHY, 5 MEH). r6 had closed with power. Each code
fix below was shown RED against the unfixed code first. The full suite was not run (bug-088); the
touched families were. {#lead}

| finding | commit | change | proof |
|---|---|---|---|
| #s-2 | `8de0c14` | A failed vector delete is PRINTED, with kind, count, cause and the `rmx embed --gc` remedy, and COUNTED on `Store.vector_delete_failures`. `sync_files`, `prune_noise` and `fold_concept_dups` report it as `vector_delete_failed`. "Not installed" is now `find_spec("lance") is None`; a broken import is a failure. The second `except: pass` in `_bulk_purge_ids` is gone. | 4 tests, RED with empty stderr, against a real non-dataset `code.lance`. |
| #s-1 | `2cd73b9` | `shared_reranker(why=)` returns the cause. `_apply_rerank_safe(warnings=)` feeds `memory_recall` / `ann_search` `warnings`, which the CLI prints to stderr and the verb carries. Score-time failures and `RerankSkipped` go on `bundle.warnings`, which appear in the JSON and the text and are merged by the context op. scan-prompt puts the cause on its bundle. | 7 tests RED on the old code. |
| #s-1 (found) | `2cd73b9` | **`build_context`'s no-anchor hand-off dropped the reranker**, so `rmx context "<phrase>"` was never reranked, although the daemon built a reranker for every such call. r7's probe could not reach `score` for the same reason as our first test: tldr-only rows with no ingest. | The spy test now sees the phrase. The mutation that drops the hand-off fails 2 tests. |
| bug-089 | `2cd73b9` | `search-dense` renders reranked hits in a `rerank score` column. | CLI test. |
| #m-3 | this commit | The offline fixture IMPORTS `huggingface_hub.constants`, so monkeypatch restores the pre-test value. A restore test runs last in the file. | The restore test is RED with the old fixture (`r7-m3-red.log`). |
| #m-4 | this commit | A partial-cache case drops only `tokenizer_config.json` (O7). An explicit `--learn` on a delegated grep prints `--learn ignored`. | O7 is now pinned. The note test is RED on the old CLI (`r7-m4-red.log`). |
| #m-2 | this commit | The r6 summary's external-calls table now has correct lines, the second implicit `npm install` (`run.sh:39`), the judge at `score.py:66` and the Fireworks provider. The user's "leave it" is recorded as the disposition. | — |
| #m-5 | this commit | Task 16.6: AC-2 is "writes nothing, measured with no grep running". AC-5 compares in one unit (evidence rows). `moved` re-pointing is raised for the spec review; d-c stands. | — |
| #m-1 | this commit | Recorded in plan-17 (compaction bounds the per-file commits; 17.1 considers skipping deletes for never-embedded ids). | — |

**Families run:** 351 + 22 passed (context, scan, recall, rerank, verbs, parity, models offline,
Lance failures). The 2 cost-budget failures were a test stub with the old `shared_reranker`
signature, now updated. 101 related store/sync/watch tests passed, plus one FSEvents timing flake,
which passed 3/3 alone (bug-091). {#tests}

**Also this session, outside the r7 range:**
- 0.76.1: the bug-085 hotfix deployed.
- 0.76.2: launchd plists export a fixed PATH (bug-090). The fleet re-rendered and all 15 plists
  are in sync.
- Hand compaction of refmatrix, viascope and cliquedb: 1.3 GB→105 MB, 925 MB→229 MB,
  1.1 GB→62 MB.
- Plans 17 and 18 drafted.

{#also}

rel: evidence-for -> [[bug_registry#registry]]
