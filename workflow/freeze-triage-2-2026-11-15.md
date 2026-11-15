---
gmd: "0.1"
id: freeze-triage-2-2026-11-15
title: "Pre-mod freeze, second triage: plans 2-15 and 21-25 the freeze line did not name"
tags: [workflow, freeze, triage, proposal, plan-24]
metadata:
  node_type: proposal
  status: withdrawn
  created: 2026-11-15
---

# Freeze triage 2: plans 2-15 and 21-25 {#root}

**WITHDRAWN (lead, 2026-11-15).** Built from file statuses instead of the consolidation ([[plan-review-2026-11-13]], the 2026-11-14 queue review). Wrong on two rows: 3.7 is merged (`91ddbe0`, 0.81.0), so plan-24's dependency is met; 25.4/25.5 are superseded by 16.5 (L42). Being rewritten over plans 2-31 (the user: "include 2-31 then").

The user, 2026-11-15: "what about 2-15, 21, 22, 23, 24, 25?". The freeze line
([[plan-of-plans#freeze]]) and the first triage ([[freeze-triage-2026-11-15]]) covered the L106
queue only. This is every plan in 2-15 and 21-25, read from each file's `metadata.status` and its
task files on master `f3a508f`, with a disposition proposed against the freeze's goal. Q31 asks
the user.

rel: amends -> [[plan-of-plans#freeze]]
rel: derives-from -> [[freeze-triage-2026-11-15]]
rel: depends-on -> [[plan-24-mod-transport]]
rel: related-to -> [[open-questions]]

## The finding that blocks the mod {#blocker}

[[plan-24-mod-transport]] `depends-on` [[task-3.7-verb-it-backlog]] and its build phase reads
"3.7 merged". 3.7 (`in-progress`, wave W2-d) is not on the freeze line, so the freeze as written
never reaches the mod's start condition. {#blocker-body}

## Table {#table}

| plan | state on master | proposal | why |
|---|---|---|---|
| 2, 8, 9 | `in-progress`; every task closed | **close now** (status → `completed`, bookkeeping by the lead) | nothing open; the status was never flipped |
| 3 | 6/7 closed; **3.7 verb-it backlog `in-progress`** | **admit 3.7** | plan-24 depends on it |
| 4, 5, 12, 14 | `completed` | — | done |
| 6 | all tasks closed; #s-3 closes with T0.4 (two named exceptions, L122) | close when T0.4 lands | already inside 29.4 |
| 7 | all tasks closed; T0.6 dense re-run, T0.7 deferral rows | close when T0.6/T0.7 land | already inside 29.4 |
| 10 | master: 10.1 + 10.2/10.3 cancelled; 10.4-10.6 and the amended 10.2/10.3 on unmerged `spec-wave-t3b` | already admitted (T3, after 31.5); merge `spec-wave-t3b` with its freshness revision then | freeze item 5 |
| 11 | `superseded` | — | — |
| 13 cross-partition sweep | `drafting`, 0/7 | **post-mod** | new machinery; not graph correctness the freeze needs |
| 15 | all shipped; reopened by ch-bsd r1 #b-3 (15.1's test wrote `src/store.py`), returns to `completed` after a full suite whose log describes the tree | **close at the next minor release's full suite** (0.85.0 gate), bookkeeping | the condition is a clean full-suite log, which every minor gate now produces |
| 21 | 21.1 done; 21.2, 21.4, 21.5 admitted; **21.3 indexed-symbol nudge, 21.7 behavioural use** unlisted | **post-mod: 21.3, 21.7** | 21.3 is a new hook nudge (the mod replaces the hook surface); 21.7 is the ablation method 31.5 step 3 reuses only if needed |
| 22 | 0/7; 22.6 R4 folded into 31.2 | rest **post-mod** (already listed) | — |
| 23 | 23.0 done; 23.1, 23.2, 23.3, 23.5 admitted (T4); 23.4 post-mod | as listed | — |
| 24 | `drafting`; specs 24.0-24.8 + 24.2a through 5 bsd rounds | **the destination**: starts when the freeze list (with 3.7) is done; specs get a freshness revision first | the freeze exists to reach it |
| 25 | 25.1 shipped in 0.83.0 (`af83867`) but `pending`; 25.2, 25.3 admitted; **25.4 grep BRE translation, 25.5 substring BRE metas** unlisted | **25.1 → `completed`** (bookkeeping); **admit 25.4, 25.5** | they are bug-167 / bug-174, cliquedb's field-report defects that the user's 2026-11-08 override put before the mod; the first triage kept 25.2/25.3 on that override and dropped these two by omission |
{#table-body}

## Effect on the freeze line {#effect}

Admitted in addition: **3.7**, **25.4, 25.5**. Post-mod in addition: **plan-13**, **21.3**,
**21.7**. Bookkeeping now: plans 2, 8, 9 → `completed`; 25.1 → `completed`. Bookkeeping at a
named event: plan-6 (T0.4), plan-7 (T0.6/T0.7), plan-15 (the 0.85.0 full suite). {#effect-body}
