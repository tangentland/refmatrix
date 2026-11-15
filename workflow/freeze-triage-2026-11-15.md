---
gmd: "0.1"
id: freeze-triage-2026-11-15
title: "Pre-mod freeze: triage of the L106 queue steps the freeze line did not name"
tags: [workflow, freeze, queue, triage, proposal]
metadata:
  node_type: proposal
  status: applied
  created: 2026-11-15
---

# Freeze triage: the L106 queue vs the freeze line {#root}

The freeze line ([[plan-of-plans#freeze]], 2026-11-15) admitted 0.83.1, plan-29, plan-30 (+30.6)
and plan-31, and did not say what happens to steps 6-15 of the queue the user approved on
2026-11-14 (L106, [[plan-review-fable-2026-11-14-queue#recommended-queue]]). That was the lead's
omission. This file proposes a disposition per step against the freeze's goal: the core
concept/graph representation more useful, context succinct and relevant, performance improved,
busywork removed, loose ends tied up. **Applied:** the user answered Q28 = a on 2026-11-15; the freeze line now carries it.

rel: amends -> [[plan-of-plans#freeze]]
rel: depends-on -> [[plan-review-fable-2026-11-14-queue#recommended-queue]]
rel: related-to -> [[open-questions]]

## Proposed disposition {#table}

| L106 step | content | proposal | why |
|---|---|---|---|
| 1 | bookkeeping; merge the seven frozen spec branches | **keep, scoped** | merge only the branches a kept step needs (each needs its freshness revision) |
| 2-5 | 0.83.1; plan-29 | keep | already admitted |
| 6 | T2: 26.5 → 26.7 → 26.6 R3 → 26.8 → 26.9 ∥ plan-27 (memory organisation + fleet rollout) | **keep** | memory-layer loose ends; the user set this order; half-done organisation is a loose end |
| 7 | G22 ∥ bug-218 (reinforcement reads edges reversed), then G30 | **keep bug-218**; G22/G30 with step 10 | bug-218 is graph correctness |
| 8 | hook window: 10.3 → 25.1b → compaction-as-handoff → agent-start; 25.2 → 25.3 → 19.0 rest | **split:** keep 25.2, 25.3 (cliquedb field bugs, the user's 2026-11-08 override) and 10.3; **post-mod:** compaction-as-handoff, agent-start, 25.1b | the mod replaces the hook surface; building new hook features now is rework |
| 9 | T4: bug-185 → 23.2 → 23.1 → 23.3 ∥ 23.5 (bounded writes, lock holds) | **keep** | daemon liveness and lock holds are performance and loose ends (0.83.1's S1 is the same class) |
| 10 | T3: 10.5 → 10.6 → 10.4 → 10.2; 21.2 → 21.4 (injection dedup, precise context) | **keep, merged with Q27-b** | this is "context succinct and relevant"; the scan-prompt reduction (plan-31 31.5) goes first |
| 11 | G32 → 21.5 phase M → 28.1-28.5 (used-signal, paired series) | **keep 21.5 phase M** (it is the STM/injection evaluation); **post-mod:** plan-28 | the evaluation decides what to cut; plan-28's live A/B can follow the mod |
| 12 | T4: 23.4 → 16.6 slice → 17.1 → 17.2 → 17.4 → 17.3 (nightly maintenance) | **post-mod** | new operational machinery |
| 13 | T6: 22.1a → 22.2 → 22.5 ∥ 22.6 → 22.3 (audited removal) | **merge 22.6 R4 into 31.2**; rest post-mod | 22.6 R4 is the learned-row keep that 31.2 needs; the rest is new machinery |
| 14 | T5: 16.1 → 16.2 ∥ 16.3 → 16.5 → 16.4; 22.1 (invisible grep shim) | **post-mod** | grep learning stays off until 31.2; the shim is a new feature |
| 15 | plan-18 (duckdb store maintenance) | **post-mod** | operational machinery |

## Effect {#effect}

Before the mod: 0.83.1; plan-29; T2 (26.5-26.9, plan-27); bug-218; 25.2, 25.3, 10.3; T4 (bug-185,
23.1-23.3, 23.5); T3 (plan-10 dedup, 21.2, 21.4) with 31.5 first; 21.5 phase M; plan-30 (+30.6);
plan-31 (with 22.6 R4 folded into 31.2). Post-mod: compaction-as-handoff, agent-start, 25.1b,
plan-28, 23.4, plans 16, 17, 18, the rest of plan-22. {#effect-body}
