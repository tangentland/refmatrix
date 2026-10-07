---
gmd: "0.1"
id: impl-remedy-bsd-r8-64117e1
title: "Remediation of ch-bsd r8 (bd59e9a..64117e1): the phrase rerank leaves the writer lock, failures reach the caller, every warning route pinned"
tags: [implementation-summary, bsd, remediation, rerank, lance, context]
metadata:
  node_type: summary
  audit: bsd-r1-remedy-r8-64117e1
  created: 2026-10-07
---

# Remediation of ch-bsd r8 {#root}

rel: implements -> [[bsd-r1-remedy-r8-64117e1]]
rel: amends -> [[impl-remedy-bsd-r7-bd59e9a]]

Round 8 was DIRTY with 7 findings (0 BULLSHIT, 4 SKETCHY, 3 MEH) and no blockers. Each fix was
shown RED first. The full suite was NOT run (bug-088); the touched families were. {#lead}

| finding | commit | change | proof |
|---|---|---|---|
| #s-2 | `797def8` | `_op_context` builds on the READ path (`_read_with_fallback`), so the rerank never holds the writer lock while a read store exists. `RemoteReranker.with_budget` bounds the op's rerank (`RMX_CONTEXT_RERANK_S`, default 3.0); an over-budget pool degrades to a warning. | A probe thread acquires the writer lock from inside `score`; RED before (lock held, no budget). 86 related tests pass. |
| #s-1 | `868845d` | `vector_delete_failed` comes back from `bulk_forget_memories`, `forget_by_selector` and `vacuum`. Every render site prints it to the caller's stderr (prune-noise, sync, memory dedup, vacuum, forget, memory forget). The watch-flush log line carries `vector_delete_FAILED=N`. | RED: `KeyError`, plus empty stderr from a real `rmx forget` on a broken dataset. |
| #s-4 | `868845d` | Seven lance test files skip only when lance is not installed. An installed-but-broken lance now fails collection, which surfaced **bug-092** (`.venv-eval` lacks `typing_inspection` outside the ambient `PYTHONPATH`). | In the clean env, collection now errors instead of skipping. |
| #s-3 | `db2750f` | One route test per surviving mutation, over a real store with real Lance vectors; only the model boundary is stubbed. | All nine (R2 R3 R3b R5 R8 R9 R10 R13 R16) FAIL now (`r8-s3-mutations.log`). |
| #m-2 | this commit | The context op's `warnings` no longer repeat the body's (a score-time degrade printed twice in text mode). The verb MERGES body and op warnings instead of overwriting. The vector-delete hint says `embed --gc` needs a working `import lance`. | The R10 test asserts the degrade appears once; there is a verb merge test. |
| #m-1 | this commit | The `launchd_path` docstring now matches this machine (`~/bin` leads through the symlink). The hub's deliberate env passthrough is named. An existence-filter test kills L3. | L3 killed. |
| #m-3 | this commit | The r6 summary says the second implicit `npm install` row is ASSUMED kept and awaits the user's confirmation. | — |

**Open, not code:**
- bug-092's env fix (`.venv-eval/bin/pip install typing-inspection`) awaits the user.
- r8's point that the MCP/daemon phrase-rerank ordering has never been measured is task 16.10's
  NL replay (the branch now reranks; the CLI replica branch does not).

{#open}
