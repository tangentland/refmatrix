---
gmd: "0.1"
id: task-26.7-memory-index-by-subject
title: "Task 26.7: build plan-19's task 19.3 — MEMORY.md grouped by compiled subject and folded by value — over the type-folder layout"
tags: [task, plan-26, memory-index, subjects, budget, plan-19]
metadata:
  node_type: task
  status: pending
  plan: plan-26-memory-organisation
  updated: 2026-11-13
---

# Task 26.7: build 19.3 {#root}

> Plan: [[plan-26-memory-organisation]]
> Status: Pending
> Depends on: [[task-26.1-layout-module-and-index-walk]], [[task-26.6-compile-subject-hygiene]]
> (live subjects, the `stale` mark), task 23.0 (sandbox; done). It does NOT wait on 19.2: see
> [[#plan-19-delta]]. Since rev 3 (2026-11-13): task 25.1 rev 7 merged, which ships in 0.83.0
> ahead of this task by user decision D-Q2 ([[plan-review-2026-11-13#d-q2]]); AC-E runs its pack.
> The 26.6 R3 residual follows this task ([[task-26.6-compile-subject-hygiene#r3-residual]], L1).

rel: part-of -> [[plan-26-memory-organisation]]
rel: realizes -> [[task-19.3-subject-tiered-index]]
rel: depends-on -> [[task-26.6-compile-subject-hygiene]]
rel: depends-on -> [[task-26.1-layout-module-and-index-walk]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget#r4]]
rel: derives-from -> [[plan-review-2026-11-13#d-q2]]

## Requirements {#requirements}

Plan-19's approved task [[task-19.3-subject-tiered-index]] already specifies the subject-grouped
index:
- one block per LIVE compiled subject, with a `--subject <slug> --k <n>` command that returns
  every member;
- value order;
- folding by value, in tiers;
- executed reachability (`rmx memory index --check-reach`);
- curated hooks preserved;
- a score snapshot;
- an atomic, locked write of the index triple.

This task builds 19.3. Its R1-R8, ACs and mutations are this task's requirements verbatim, except
for the delta below. The round-0 shape ("one `## label (N)` header per subject") is withdrawn,
because plan Q6 defers to 19.3.

### What is built from 19.3, and what differs {#plan-19-delta}

| 19.3 item | here | difference |
|---|---|---|
| R1 subject block (live subjects only; stale ones hidden per 19.4 R5) | built | Subjects of scope `pattern` (26.6 R-A) are excluded from a project memdir's index. They belong to the impressions layer (26.9). |
| R2/R3 value order, tiered fold | built | Until 19.2 lands, scores are 19.3 R7's VIRTUAL scores, computed from files alone. When 19.2 lands it supplies real scores through the same snapshot input, and 26.7's code does not change. |
| R4 operational reachability + `rmx memory index --check-reach` | built | none |
| R5 subjects/scores source (replica op outside the daemon; writer store inside) | built | none |
| R6 hooks preserved | built on 26.1's id-keyed hooks | Hooks are keyed by memory id, not path, so they survive the 26.5 moves (B4). This amends 19.3 R6. |
| R7 score snapshot | built | Virtual scores until 19.2 (above). |
| R8 atomic, locked triple | built | 26.1's carried-prose block is part of `MEMORY.md` inside the triple. |
| (new) the type-folder layout | entries link `feedback/x.md` etc. via 26.1's walk | not in 19.3 |
| (new) carried prose and the content guard | from 26.1 AC-5/AC-6 | not in 19.3 |

**What plan-19's owner records when this lands** (plan-19 files are not edited here):
- 19.3 is realized by task-26.7;
- the score source stays open pending 19.2.

## Acceptance criteria {#acceptance}

- **AC-0:** 19.3 AC-1 through AC-10 pass in task 23.0's sandbox, on copies of this project's
  memory dir (organised layout) and catalog, with the virtual scores.
- **AC-A:** a pattern-scope subject never renders in a project index.
- **AC-B:** prose carried by 26.1 survives a 19.3 render byte-for-byte, and its characters count
  against the budget.
- **AC-C:** after 26.5 moves a file, its curated hook appears on its subject or type line
  unchanged.
- **AC-D: marker-gated (r2 s2).** The 19.3 render runs only in a memdir with `.memory-layout`.
  An un-organised dir gets HEAD's render (26.1 AC-9), so the deploy does not re-render fleet
  indexes before plan-27 backs them up. Test: one twin with the marker and one without.
- **AC-E: 25.1's curated-hook lookup survives the regroup (D-Q2, rev 3).** See [[#ac-e]].

## Files to Create / Modify {#files}

19.3's [[task-19.3-subject-tiered-index#files-to-modify]] list applies:

| file | change |
|---|---|
| `src/refmatrix/memory_index.py` | per 19.3 |
| `src/refmatrix/daemon.py` | the live-subjects read op |
| `src/refmatrix/handoff.py` | `_ss_update_index` |
| `src/refmatrix/cli.py` | `rmx memory index --check-reach` |
| `tests/test_memory_index.py` | extend |
| `tests/test_memory_index_reach.py` | create |
| `tests/test_memory_index.py`, plus one end-to-end case through `rmx memory recall --pack` | AC-E (rev 3) |

## Test Strategy {#test-strategy}

Follows 19.3's test strategy:
- the task 23.0 sandbox;
- copies of the memory dir and the catalog;
- a character-count budget, checked with a multibyte fixture;
- R4's executed check.

Mutations: 19.3's list, plus:
- render a pattern-scope subject → AC-A goes RED;
- key hooks by path → AC-C goes RED.

## Revision round 1 (2026-11-09) {#rev-round-1}

| finding | change | anchor |
|---|---|---|
| B1 (re-specifies approved 19.3) | Builds 19.3; `realizes` edge; delta table; plan-19 record list | [[#plan-19-delta]] |
| Q6 verdict (defer to 19.3) | Round-0 header shape withdrawn | [[#requirements]] |
| B4 (hooks keyed by path) | 19.3 R6 amended to id-keyed hooks (26.1) | [[#plan-19-delta]], AC-C |
| M9 (25.1 depends on 26.7, which collided with 19.3) | Ownership resolved: 26.7 IS 19.3's build | [[#requirements]] |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

| finding | change | anchor |
|---|---|---|
| s2 (the deploy re-renders fleet indexes) | The 19.3 render is marker-gated; twin test | AC-D |

## Revision round 3 (2026-11-13): D-Q2 {#rev-round-3}

Answers [[plan-review-2026-11-13#d-q2]] (spec gap G6, [[plan-review-2026-11-13#spec-gaps]]).
Evidence: `workflow/review-output/pop-2026-11-13/contra-a.md` Ca-1. The user's D-Q2 ships 25.1
rev 7 in 0.83.0, before this task. That waives, on the record, the order "26.7 (19.3) closes
before 25.1 starts" ([[plan-26-memory-organisation#overlap-37]]). The price of the waiver is this
AC: 25.1's pack reads curated hooks out of the index that this task regroups. Status is unchanged
(`pending`).

rel: derives-from -> [[plan-review-2026-11-13#d-q2]]

| row | change | anchor |
|---|---|---|
| D-Q2 / Ca-1 (25.1 ships before the regroup; no 26.7 AC protects its hook lookup) | AC-E; 25.1 rev 7 merged is a dependency | [[#ac-e]], header |
| L1 (26.6 R3 residual after 26.7) | Header records the order; no AC change | header |
| Q8 open (brief rule) | No line here changes under Q8 b | [[#q8-b]] |

### AC-E: the curated-hook lookup survives the regroup {#ac-e}

25.1's pack builds its hook map with `memory_index.load_hooks(memdir)` and looks a row up by its
memory id first, then by its path relative to the memdir
([[task-25.1-recall-hook-byte-budget#r4]]). The 19.3 render changes which index lines exist:
- subject blocks;
- a memory listed under two subjects;
- tier folds;
- type lines for memories in no live subject.

Because `load_hooks` lets an index hook replace the sidecar value, a render line that carries a
different or a cut hook would rewrite a curated hook (bug-193's family).

The fixture copies an organised memdir, with curated hooks on at least five memories, chosen so
that each of these is covered:
- a memory listed in one subject block;
- a memory in two subject blocks;
- a memory folded behind a tier fold;
- a memory in no live subject (on its type line);
- a memory that 26.5 moved (AC-C).

- **(a)** `load_hooks(memdir)` returns the same hook for each of those ids before the 19.3 render
  and after it, byte-identical. A hook is never replaced by subject-line text, by a fold line, or
  by a cut ending in `…`.
- **(b)** Two consecutive renders leave `.memory_hooks.json` byte-identical, and
  `rmx memory index --check` reads in sync after the second (idempotent, bug-050).
- **(c)** In the task 23.0 sandbox, the real `rmx memory recall --pack` (25.1 R3/R4), run over that
  memdir's store, prints each named hit's curated hook and not its first sentence. This is 25.1
  AC-9's id-keyed case re-run on the regrouped dir.
- **(d)** On the marker-off twin, 25.1 AC-9's path-keyed case passes unchanged (AC-D).
- **Mutations, each killed:**
  - a subject-block member line rendered with a shortened hook that `load_hooks` reads back kills
    (a);
  - dropping folded entries from `save_hooks` kills (a) and (c) for the folded memory;
  - keying the 19.3 render's hooks by path kills (c) for the moved memory.

### Lines that change under Q8 b {#q8-b}

None. The index and its hooks live on the file side. Save-state pointer lines are rendered from
files, whether or not save-states are bridged.
