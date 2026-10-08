---
gmd: "0.1"
id: plan-19-adaptive-memory-budget
title: "Plan 19: memory reaches the agent within budget, ranked by use, grouped by subject, and never lost"
tags: [plan, memory, recall, hooks, budget, memory-index, adaptive]
metadata:
  node_type: plan
  status: drafting
  created: 2026-10-07
---

# Plan 19: adaptive memory under the context budgets {#root}

**Date:** 2026-10-07
**Status:** Drafting. Task specs 19.1–19.5 are written; spec review is next.
**Origin:** the user, 2026-10-07: "we need a way to automatically optimize memory storage and
retrieval to make it adaptive to keep more than the byte limit". Decisions are recorded in
[[exploration-adaptive-memory-budget]]: B + A + D now, a new plan, and first after the remedy merge.

rel: derives-from -> [[exploration-adaptive-memory-budget]]
rel: depends-on -> [[refmatrix/adr-0004-unified-location-space-index]]
rel: depends-on -> [[feedback_decay_never_loses_knowledge]]
rel: depends-on -> [[reference_hook_output_10k_cap]]
rel: related-to -> [[plan-17-nightly-store-maintenance]]

## Why {#why}

Memory reaches the agent through budgeted channels, and today most of what they produce never
arrives:
- **SessionStart recall** (`hooks.py:277`, `--session-start --k 10 --json`) emitted **26,567 B**.
- **Per-prompt recall** (`hooks.py:313`, `--stdin-json --k 5 --json`) emitted **16,347 B**.
- Claude Code delivers hook output whole only up to about **10k chars**
  ([[reference_hook_output_10k_cap]]). Above that, the agent gets a ~2 KB preview. So about 1 of 10
  and 1 of 5 hits are seen, and the rest is produced and paid for unread.
- **`MEMORY.md`** is at 22,812 / 24,000 chars (95%). It folds projects by **file mtime**
  (`memory_index.py:275`), never by value; feedback never folds.
- **Nothing records which memories are used**: no recall count, no last-recalled, and 0
  memory-recall rows in `query.log`. Every selection rule is recency or a hand-fixed order.

{#why-body}

## Goal {#goal}

Every injection channel delivers as much memory as fits under its real budget, chosen by measured
use, and grouped so one line can stand for many memories. Nothing is lost: a memory that does not
fit is reachable by name, by subject or by recall, and decay only demotes
([[feedback_decay_never_loses_knowledge]]).

## Design {#design}

- **Pack, don't truncate (19.1).**
  - `memory recall --max-chars N --pack` emits a compact text payload: one hook line per hit
    (name, title, one-line hook, id), full bodies for the top hits only while the budget allows,
    and a trailer naming what was left out and how to fetch it.
  - The hooks use it with N under the measured harness threshold (default 9,500, env
    `RMX_HOOK_BUDGET_CHARS`). `k` stops being the binding constraint: the budget is.
- **Count use, exactly and without losing anything (19.2).**
  - Every memory gets a lifetime record that never decays (`first_seen`, `last_seen`,
    `lifetime_hits`, `lifetime_used`) and a decaying recency score with a floor.
  - Memories are a small domain (≈500 rows), so the counts are EXACT, not sketched.
  - Recall hits and uses are appended to a queue (the `learn_queue` pattern, no lock) and drained
    in batches by the daemon tick. That avoids a write per event, the bug-085 lesson.
- **Subject-tiered, value-ranked index (19.3).**
  - `MEMORY.md` renders one line per compiled subject, with its top members inline by score.
  - Folding is by score, not mtime. Feedback and other asserted memories have a higher floor and
    fold only behind it.
  - Every folded memory stays reachable through its subject line and through recall.
- **Keep the derived layers current (19.4).**
  - Memory compile runs on a schedule: plan-17's nightly tick, or on save-state until that tick
    exists.
  - The index is regenerated on every memory write the bridge sees, and at SessionStart, not only
    at save-state.
- **Measure delivery, not production (19.5).** Per channel: distinct memories VISIBLE to the agent
  (inside the delivered payload) before and after, and the harness threshold probed directly.

{#design-body}

## What we give up {#tradeoffs}

- **The hooks stop emitting JSON.** The JSON output (`--json`) stays for programmatic callers, but
  the hooks switch to `--pack` text. A consumer that parsed hook JSON would break. None exists:
  the hook output goes only to the agent's context.
- **Bodies are no longer always inline.** The top 1–2 hits carry bodies; the rest carry a hook line
  and a fetch pointer. That trade is deliberate: 10 hook lines the agent sees beat 10 bodies it
  does not.

{#tradeoffs-body}

## Tasks {#tasks}

| task | what | acceptance (summary) |
|---|---|---|
| 19.1 | `--max-chars` / `--pack` for `memory recall`; hooks use it | each hook's payload ≤ budget; visible distinct memories ≥ 5x today on the same prompts |
| 19.2 | exact lifetime + decaying recency usage record, queued and drained | hits and uses counted exactly; decay never below the floor; no write under `_store_lock` per event |
| 19.3 | subject-tiered, value-ranked `MEMORY.md` | fits the cap with more memories reachable; no memory unreachable; asserted floor holds |
| 19.4 | compile on schedule; index on every bridged write and at SessionStart | a new memory appears in the index without a save-state; subjects refresh nightly |
| 19.5 | delivery measurement + harness threshold probe | before/after table per channel in the implementation summary |

Task specs: `workflow/plans/plan-19-adaptive-memory-budget-tasks/`.

## Decisions {#decisions}

| # | decision | source |
|---|---|---|
| d-1 | B (packing) + A (usage) + D (subjects) now | user, 2026-10-07 |
| d-2 | budget = just under the harness's whole-delivery limit (~10k chars), measured, configurable | user ("as high as 10k"), 2026-10-07 |
| d-3 | low-value feedback may fold behind a floor; never lost | user rule "decay is fine, losing knowledge is bad", 2026-10-07 |
| d-4 | own plan; subjects compiled on plan-17's tick | user, 2026-10-07 |

## Out of scope {#out-of-scope}

- Concept-level counters and helix age tiers: ADR-0004's helix plan.
- Changing what memories ARE (the GMD format, MEMORY-RULES): this plan changes selection and
  delivery only.
