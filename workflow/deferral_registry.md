---
gmd: "0.1"
id: deferral_registry
title: "Deferral Registry — deferred production functionality"
tags: [process, deferral, governance]
metadata:
  node_type: registry
---

# Deferral Registry {#root}

Companion to [[test_mock_registry]]. Where the mock registry classifies **test-side mocks**, this
registry tracks **deferred production functionality** — features intentionally not built yet,
shipped as **fail-closed seams** (an honest `feature_not_supported`-style raise), **inert
self-sentinels**, or **scaffolding with no current caller** — each gated on a concrete future
trigger (an Accepted-but-unimplemented ADR, a later phase, or a platform/deployment).

rel: part-of -> [[test_mock_registry]]

A deferral is **legitimate** only if it (a) fails closed or is inert — never a silent wrong
answer — and (b) names a concrete graduation trigger with an owner. A deferral that silently
self-resolves, or has no graduation owner, is a **bug**, not a deferral. `@ch-gap-master` curates
this registry; `@ch-bsd` flags stale deferrals.

## Classification {#classification}

| Classification | Meaning | Behavior now |
|----------------|---------|--------------|
| `fail-closed-seam` | Real seam that raises/refuses on the unbuilt path | Refuses honestly |
| `inert-sentinel` | Placeholder value/branch with no active effect | No effect |
| `scaffold-no-caller` | Structure built ahead of its first caller | Unreachable in prod |

## Registry {#registry}

| Item | Location | Classification | Graduation Trigger | Owner |
|------|----------|----------------|--------------------|-------|
| rewriter hook bakes the generator's tree (bug-008, recurring) | src/refmatrix/search_hooks.py `render_scripts` (`RMXGREP =`/`RMXRG =` absolute paths in `~/.claude/hooks/rmxgrep-rewrite.py`) | GRADUATED 2026-09-16 (task 6.5) | runtime wrapper resolution + a foreign-tree refusal on the user-global dir, both landed and mutation-checked; `tests/test_search_hooks.py` 24 passed. Live regen still pending a deploy — see the bug-008 row | plan 6 |
| `rmx memory sync-disk` alias of `ingest-gmd --as-memory` (bsd-plan5-r2 #b-2-r2) | src/refmatrix/cli.py `memory_sync_disk` (15 lines; forwards to `_sync_memory_dir`) | `scaffold-no-caller` (in this repo; the callers are the fleet's copies of the p20-0 compiler) | every cat-herder project's `.claude/p20-0/compile_guardrails.py` (template at ~/at/bdep/cat-herder, 8 fleet copies under ~/github/atollogy/bdep) calls `ingest-gmd --as-memory` — `grep -rl 'memory sync-disk' ~/github/atollogy/bdep/*/.claude ~/at/bdep/cat-herder` empty → delete the alias + `test_sync_disk_is_a_thin_alias_of_the_bridge` | user (template + fleet re-seed); this repo's copy already converted |
| LongMemEval Layer B (answer model + LLM judge) | `eval/production/longmemeval/` (not built) | `scaffold-no-caller` (nothing built; the seam is the missing file) | Layer A shows non-floor Recall@20 on at least one surface AND a budget decision. MemAware's Layer B was BUILT and never affordably run — that is the outcome this deferral exists to avoid repeating. | plan 7 |
| `longmemeval_m` variant (500 sessions/question) | `eval/production/longmemeval/prepare.py --split m` (fetch works; corpus never built) | `fail-closed-seam` (the flag exists and the build would simply take days) | `_s` results show the union mode saturating, i.e. the haystack is too easy to discriminate surfaces. ~250k session docs at current ingest throughput. | plan 7 |
| CLI candidate-set prefilter for recall (`ann_search(candidate_ids=...)` has no flag) | `src/refmatrix/recall.py` (API exists, `test_dense_recall_respects_candidate_prefilter`); no CLI surface | `scaffold-no-caller` | LongMemEval `restricted` mode is a deep-retrieve + post-hoc filter BECAUSE of this; a real flag removes the approximation and its recall ceiling. Graduates when the ceiling measurably caps a comparison. | plan 7 |
| Answer-usefulness as the retrieval-miss signal (vs `cardinality == 0`) | helix layer (retrieval timestamps exist); no join to whether a hit was read | `scaffold-no-caller` | The second finding of the `brief/unanswered` gate: a query returning 20 rows nobody used is a better miss than one returning zero. Blocked behind the helix phase-2 storage fork. | plan 8 |
| `brief/stale` detector | `src/refmatrix/brief.py` (class documented in plan 8, not implemented) | `scaffold-no-caller` | Needs mutable edge-time columns; deferred until helix phase 2 picks its storage fork, so the losing fork is not baked in. | plan 8 |
| 28% of `scan-prompt` calls return nothing | `src/refmatrix/scan.py` (behaviour, not a stub) | `inert-sentinel` (the surface runs and yields an empty bundle) | Found incidentally by task 10.1: 112 of 400 replayed real prompts produced zero entries from the surface that fires on EVERY prompt. Unknown whether that is correct on control prompts ("yes", "go") or a retrieval gap. Graduates when a run that separates control prompts from substantive ones attributes the 28%. | plan 10 (follow-up) |
| Re-measure big-store query latency on a SETTLED store | `/Volumes/littlebig/longmemeval/` | `fail-closed-seam` (the measurement is simply not taken) | The 62.9 s was measured during a 432 MB adjacency-cache build + 3-slot catalog replication. Those artifacts now exist, so a restart should not repeat it. Blocked behind the open @ch-bsd findings per user gate. | plan 7 |

## Graduation Log {#graduation-log}

| Date | Item | Trigger fired | Notes |
|------|------|---------------|-------|
| 2026-09-16 | Rerank windows the doc instead of taking its head | Shipped in `d232baa` (task 12.3) | `reranker.window_doc` keeps half the budget on the head and windows the rest around the query, at BOTH cut points. The planned KWIC-only window measured WORSE than the head it replaced (502 vs 541 of 896); the split scores 672. Below `WINDOW_MIN_CHARS`=1024 truncation is byte-identical, so `memory recall`'s 700-char hook leg is unchanged — `scan-prompt`'s bundle leg is at 2048 and IS windowed. Coverage claim only: `workflow/measurements/rerank-window-ab-0916.md`. |
| 2026-09-16 | Attribute the ~8.5 s CLI-vs-`build_context` gap | Shipped in `f97bcf4` (task 12.6) | Two causes. A real defect: the grep floor greped `$HOME` for memory-only stores — 15.09 s, hard timeout, zero hits, swallowed (bug-040, fixed, 15.13 s → 0.09 s). The residual is cold first-touch I/O on an SD-card volume (94.7 MB/s, 432 MB adjacency cache = 4.6 s). `RMX_TIME_PHASES=1` ships the instrument. `workflow/measurements/cli-startup-gap-0916.md`. |
| 2026-09-16 | `RMX_INVOCATION_SOURCE` on `query.log` rows | Shipped in `4ae41ce`, two commits after the row was written | Row was stale inside its own range (ch-bsd r1 #s-14). Verified on the wire: `{"kind":"context","source":"context-replica","invocation":"hook"}`. A live field left in the registry sends a future agent to re-implement it. |
