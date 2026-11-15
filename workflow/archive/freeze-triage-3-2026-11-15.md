---
gmd: "0.1"
id: freeze-triage-3-2026-11-15
title: "Pre-mod freeze, third triage: every plan from 2 to 31, task by task, and the mod's real start condition"
tags: [workflow, freeze, triage, proposal, plan-24, queue]
metadata:
  node_type: proposal
  status: archived
  created: 2026-11-15
  author: ch-architect (Fable 5.2)
---

# Freeze triage 3: plans 2 to 31, task by task {#root}

> **ARCHIVED 2026-11-15** (the user: "archive any other doc that acts as an alternate source of truth").
> Not a source of truth: order, scope, status and the live L / D / Q ledgers are in [[plan-of-plans]];
> finished items are in [[pop-finished]]. This file is kept unchanged otherwise, as history and evidence;
> its ids and anchors still resolve.


The user, 2026-11-15: "include 2-31 then". This file is a **compilation of what is already
agreed**, not a new triage. It answers one question: what remains before the mod (plan-24) can
start? It replaces the withdrawn second triage, which read each file's `metadata.status`. Those
statuses are stale, so this one reads decisions and merge commits. It applies two layers in
order: the consolidation ([[plan-review-2026-11-13]], L1-L124, and the 2026-11-14 queue the user
approved, L106), then the prioritised version of 2026-11-15 ([[plan-of-plans#freeze]],
[[plan-of-plans#post-mod]], Q28 = a). The freeze's own rule settles everything else: an item the
freeze line does not admit is post-mod. Only two things are flagged: a contradiction between the
layers, and a dependency of plan-24's start that is neither met nor admitted ([[#flags]]). The
user answered the flags it first raised on 2026-11-15 (Q32-Q36 = a; L128, L129 in
[[plan-of-plans#rulings]]), and this text carries those answers.

The table was read on `master` at `944335e` and re-checked at `ad5df99`, after the six spec
branches and T0.1' merged. The state it compiles is carried into the POP by
`pop-rewrite-draft` (applied to [[plan-of-plans]] 2026-11-15), which is the deliverable; this file is its working paper and is archived
when the rewrite lands. No test was run. {#root-lead}

rel: supersedes -> [[freeze-triage-2-2026-11-15]]
rel: amends -> [[plan-of-plans#freeze]]
rel: derives-from -> [[freeze-triage-2026-11-15]]
rel: derives-from -> [[plan-review-2026-11-13#lead]]
rel: derives-from -> [[plan-review-2026-11-13#decisions]]
rel: derives-from -> [[plan-review-fable-2026-11-14-queue#recommended-queue]]
rel: derives-from -> [[plan-review-fable-2026-11-14-store#readiness]]
rel: derives-from -> [[plan-review-fable-2026-11-14-memory#readiness-table]]
rel: depends-on -> [[plan-24-mod-transport]]
rel: depends-on -> [[plan-29-code-quality]]
rel: depends-on -> [[plan-30-materialisation]]
rel: depends-on -> [[plan-31-pre-mod-loose-ends]]
rel: related-to -> [[open-questions]]
rel: evidence-for -> `pop-rewrite-draft` (applied to [[plan-of-plans]] 2026-11-15)

## The answer in brief {#answer}

**The mod's start condition, in five lines.**

1. Plan-24's one declared dependency on built work, task 3.7, is met: merged `91ddbe0`, released
   0.81.0 (`021f3af`).
2. Plan-24 itself is not approved. It is `drafting`: six ch-bsd rounds on 2026-10-20, the last
   DIRTY (0B/1S/1M), a seventh fold never confirmed. The user's 2026-11-08 order reads "spec r7 →
   approval → 24.0/24.1" ([[pop-finished#override-2026-11-08]]).
3. Its specs need a freshness revision first, as T0 did. Nine of the ten date from 2026-10-20.
   Decision D1 was superseded by the user on 2026-11-13 (D-Q5) and the plan does not say so. The
   modules the specs name are split by plan-29 and extended by plan-30.
4. Its two undecided dependencies are now decided (L128): the freshness revision to approval is
   the freeze's last step, with 31.5, 21.5 phase M and 30.6 as its evidence in place of the
   charter decision; and 24.6 takes the tool-event builder that 21.5's frozen build phase held.
5. The freeze list comes before it. 0.84.0 and T0.1' are done and the six spec branches are
   merged. 48 distinct pieces of admitted work remain (29.4 is in progress); plan-10's dedupe
   moved post-mod with 25.1b, and G22, G30, G32 and the `rel:` probe were admitted.

**Counts** (task ids; a plan with one fate counts each of its tasks; plan-24's ten tasks are the
mod and are not counted). {#counts}

| disposition | task ids |
|---|---|
| done | 67 |
| superseded | 3 |
| cancelled | 1 |
| dormant | 8 |
| admitted pre-mod | 57: 48 distinct pieces of work, plus 9 rows hosted inside one of them (the four closure gates, plan-2's #s-3 rider, 19.3, 19.4, 22.6 R4, and T0 as 29.4's body) |
| post-mod, named on the list since Q28 | 28 |
| post-mod, named by L128 | 18 |
| post-mod by the freeze rule only | 1 |

## Method {#method}

- **Authority, latest first:** the freeze line and post-mod list ([[plan-of-plans#freeze]],
  [[plan-of-plans#post-mod]]) with Q23-Q30; the lead rulings L1-L124 and the user decisions D-Q1
  to D-Q7 ([[plan-review-2026-11-13#lead]], [[plan-review-2026-11-13#decisions]]); the three
  2026-11-14 reviews and their `#decided` lines; `git log master`; file statuses last.
- **"Done" needs a sha** that is an ancestor of `master`. Each sha below was checked with
  `git merge-base --is-ancestor`.
- **"Post-mod (freeze rule)"** means: the freeze line does not admit it and the post-mod list
  does not name it, so the rule ("Nothing else is admitted before the mod except a bug that
  breaks something live") makes it post-mod. The row gives its last decided state. No new
  disposition is proposed anywhere in this file.
- **Spec branches** were first read at their tips (`spec-wave-t2` `0fd8a2f`, `-t3a` `8e8e307`,
  `-t3b` `5559d20`, `-t3c` `01c1f63`, `-t4` `b409d98`, `-t56` `fa1af7d`). All six have since
  merged as they stand (`3be7676`, `88c2900`, `e2010bd`, `b1be2e4`, `327703d`, `0a40f4b`), so
  the "stale status" notes that say "absent on master" or "only on a branch" are history.
- **Not found:** the queue review's `#recommended-queue` carries no row-by-row status notes on
  `master` at `944335e`. {#method-list}

## The table {#table}

Columns: the task or group; `n` = task ids in the row; the real state with its evidence; the
disposition; the file status where it disagrees. "Item 2" to "item 5" are the numbered items of
[[plan-of-plans#freeze]]. {#table-lead}

### Plans 2 to 15 {#table-2-15}

| task | n | real state (evidence) | disposition | stale status |
|---|---|---|---|---|
| 2.1-2.3 | 3 | built; remedy rounds merged through r7 (`be71e38`) | done | none |
| plan-2 rider r9 #s-3 | 1 | open; hosted by 23.5's folded rider | admitted (item 5, inside 23.5) | none |
| plan-2 riders r9 #s-2, #m-4 and r5's rerank rate | 1 | open; hosted by `task-25.1b` R16, R17, R0 (D-Q6, L51). Plan-2 closes when they land | post-mod (25.1b) | POP row 2 names 19.1 and 19.5 as hosts |
| 3.1-3.6 | 6 | merged `8ba4799`; 3.4-3.6 released 0.80.1 (`391c15c`) | done | none |
| 3.7 | 1 | merged `91ddbe0`, released 0.81.0 (`021f3af`); plan-3 closed by D-Q6 | done | task `in-progress`; plan-3 `in-progress`; POP row 3 |
| plan 4 (4.1-4.6) | 6 | released 0.80.0 (`535231e`) | done | none |
| plan 5 (5.1-5.3) | 3 | completed (POP row 5) | done | none |
| 6.1-6.5 | 5 | built; ch-bsd r1 findings open | done | none |
| plan-6 gate W2-a | 1 | = T0.4, inside 29.4 (D-Q6); closes with two named exceptions (L122) | admitted (item 2) | none |
| 7.1-7.4 | 4 | built; symbolic results reported | done | 7.4 says "dense blocked on bug-030", fixed 2026-09-16 |
| plan-7 gate W2-c | 1 | = T0.6, the dense and fused re-run in 29.4's lane | admitted (item 2) | none |
| plan-7 W4-a deferral rows | 1 | "no host plan; backlog" (L33; T0 amendment 8) | post-mod (named by L128) | none |
| 8.1-8.4 | 4 | built; 8.4 is a negative result | done | none |
| plan-8 gate W2-b | 1 | = T0.5 | admitted (item 2) | none |
| plan-8 deferral rows 43, 44 | 1 | held with the frozen 19.2 (L48 O3) | post-mod (freeze rule; 19.2 is named) | none |
| plan 9 (9.1-9.3) | 3 | built; riders closed with 21.1; closed by D-Q6 | done | plan-9 `in-progress`; POP row 9 |
| 10.1 | 1 | measured; negative result | done | none |
| 10.3 | 1 | approved spec on `spec-wave-t3b`; unbuilt | admitted (item 5) | master: `cancelled (10.1 did not clear)` |
| 10.5, 10.6, 10.4, 10.2 | 4 | approved specs on `spec-wave-t3b`; unbuilt; each header says "25.1b MERGED" | post-mod (L128: moved with 25.1b; the freeze had admitted them) | master: 10.2 `cancelled`, the other three absent; POP row 10 |
| plan 11 | 1 | never built | superseded (the user, 2026-10-07) | none |
| plan 12 (12.1-12.6) | 6 | deployed 0.72.0 (POP row 12) | done | none |
| plan 13 (13.0-13.6) | 7 | none built | dormant (C9, d4b: waits for a sessions gold set) | tasks `pending` under a dormant plan |
| plan 14 (14.1-14.4) | 4 | completed; its re-measure moved to 16.4 | done | none |
| 15.1-15.4 | 4 | built and deployed at 0.76.0 | done | none |
| plan-15 gate W1-e | 1 | = T0.7, with T0.8 (bug-196, L48) | admitted (item 2) | none |

### Plans 16 to 23 {#table-16-23}

| task | n | real state (evidence) | disposition | stale status |
|---|---|---|---|---|
| 16.1-16.5 | 5 | approved; revised on `spec-wave-t56`; unbuilt | post-mod ("plan-16") | plan body says "Drafting" |
| 16.6 Wave-1 slice | 1 | approved; revised on `spec-wave-t4`; unbuilt | post-mod ("the 16.6 slice") | none |
| 17.1-17.4 | 4 | approved; unbuilt | post-mod ("plan-17") | none |
| 18.1 | 1 | merged `530660e`, 0.79.0 | done | none |
| 18.2, 18.3 | 2 | approved; unbuilt | post-mod ("plan-18") | none |
| 19.0 | 1 | R1 is built by 25.3's STM half (L41). R0, R2-R7 and R1's rebuild remainder are unbuilt; it owns bugs 100, 103, 104 | post-mod (named by L128): follows 25.3 (L41) | `pending` |
| 19.1 | 1 | R1-R8 shipped as 25.1 (`d44e359`, L14); its riders moved to 25.1b | done | `pending` |
| 19.2 | 1 | frozen until the experiment reports (D-Q3) | post-mod (named by L128) | `pending` |
| 19.3 | 1 | built by 26.7 (L14); its value fold stays virtual (L51) | admitted (item 5, as 26.7) | none |
| 19.4 | 1 | shipped as 26.6 (`8a867bc`); R3 is the 26.6 R3 residual; R1's tick belongs to 17.2 (L28) | admitted (item 5, the residual); the tick is post-mod with plan-17 | `pending` |
| 19.5 | 1 | R1 shipped in 25.1; the rest frozen (L26); its rerank rider is 25.1b R0 | post-mod (named by L128) | `pending` |
| 19.6 | 1 | R8a is 10.3, R5-composite is 10.6 (L14); phasing, cache and Table C frozen (D-Q3) | post-mod (named by L128) | `pending` |
| plan 20 (20.1-20.3) | 3 | specs written; 20.1 waits on the user's 50-pair review; 20.2 needs G22 and bug-216 live | post-mod (named by L128) | none |
| 21.1 | 1 | released 0.80.0 (`535231e`); AC-6 fixture `69ecb21`, RED only on bug-196 (T0.8) | done | POP row 21: "BLOCKED on the user's cut" |
| 21.2 | 1 | approved; revised on `spec-wave-t3a`; unbuilt | admitted (item 5) | none |
| 21.3 | 1 | frozen (D-Q3); needs 16.1 and 16.2 | post-mod (named by L128) | `pending` |
| 21.4 | 1 | approved; revised on `spec-wave-t3a`; unbuilt | admitted (item 5) | none |
| 21.5 phase M | 1 | rev 4 approved on `spec-wave-t3c`; a measurement with no `src/`; needs G32 | admitted (item 5) | master holds rev 3.1, `pending` |
| 21.5 phase B | 1 | frozen until the charter decision (D-Q4) | post-mod (named by L128) | none |
| 21.6 | 1 | a row in plan-21's task table: "after 24.6 R4 ships" | post-mod (named by L128) | none |
| 21.7 | 1 | `drafting`, no spec (Q6, session f0521bff) | post-mod (named by L128) | none |
| 22.1, 22.1a, 22.2, 22.3, 22.5 | 5 | approved; unbuilt | post-mod ("plan-22 except 22.6 R4") | plan body says "Drafting" |
| 22.6 R4 | 1 | approved on `spec-wave-t56`; unbuilt | admitted (item 5, folded into 31.2) | none |
| 22.6, the rest | 1 | same spec | post-mod ("plan-22 except 22.6 R4") | none |
| 22.4 | 1 | blocked on plan-20 | dormant (deferral rows, L22) | none |
| 23.0 | 1 | released 0.79.1 (`d4bf001`) | done | none |
| 23.2, 23.1, 23.3, 23.5 | 4 | approved; revised on `spec-wave-t4`; unbuilt. The store review splits 23.1 into 23.1b, 23.1a, 23.1c | admitted (item 5, T4) | plan-23 body says "Drafting" |
| 23.4 | 1 | a read-only measurement; needs its re-pin | post-mod ("23.4") | none |

### Plans 24 to 31 {#table-24-31}

| task | n | real state (evidence) | disposition | stale status |
|---|---|---|---|---|
| plan 24 (24.0-24.8, 24.2a) | 10 | `drafting`; ch-bsd r6 DIRTY (0B/1S/1M), r7 fold unconfirmed | the mod (see [[#mod-start]]); not counted | POP row 24: "partial (1)"; `#phase-now`: "start now" |
| 25.1 | 1 | merged `d44e359` and `d1be40a`; released 0.83.0 (`af83867`) | done | task `pending`; plan-25 "not started" |
| 25.1b | 1 | approved on `spec-wave-t3a`; unbuilt; hosts bug-182 (R15), bug-224 (R18) and plan-2's riders | post-mod ("25.1b") | none |
| 25.2 | 1 | unbuilt; built only if its R0 replay passes L34's bands, else dropped (L43); R0 needs G32 (L54) | admitted (item 5) | none |
| 25.3 | 1 | unbuilt; the STM half always builds; the helix half follows 25.2 and 10.3 (L16, L43) | admitted (item 5) | none |
| 25.4, 25.5 | 2 | nothing left to build (L32, L42); bug-167 and bug-174 close when 16.5 lands | superseded by 16.5 | master `pending`; `superseded` only on `spec-wave-t56` |
| 26.0-26.4 | 5 | merged `61b3bde`, `9b2c4ac` + `25af9ca`, `05164ce` + `078c951`, `fdc6359`, `0c74872`; 0.82.0 (`9432b83`) | done | 26.1 and 26.4 `pending` |
| 26.6 | 1 | merged `8a867bc` (0.82.0); its R3 residual is open | admitted (item 5, "26.6 R3") | `in-progress` is right |
| 26.5, 26.7, 26.8, 26.9 | 4 | approved; revised on `spec-wave-t2`; unbuilt | admitted (item 5, T2) | plan-26 `approved` with six tasks shipped |
| plan 27 (27.0-27.6, 27.2a) | 8 | approved; revised on `spec-wave-t2`; unbuilt; the start is delegated (L78) | admitted (item 5) | none |
| plan 28 (28.1-28.5) | 5 | approved on `spec-wave-t3c` only; one paired leg (L83) | post-mod ("plan-28") | no file and no POP row on master |
| 29.4 | 1 | stage 0 merged `3b930e4` (L121); stage 1 (T0.1') merged `a0c7560` (L126); stages 2-5 remain | admitted (item 2) | task `pending`; plan-29 `approved` |
| 29.1, 29.5, 29.3, 29.2, 29.6 | 5 | approved (`b12724d`); not started | admitted (item 2) | none |
| 29.7 | 1 | spec branch `spec-29-7-learned-rekey` at `a63d120`, unmerged | cancelled (L115) | none |
| 30.0-30.5 | 6 | approved (`df75516`, L117); not started | admitted (item 3) | POP row 30 says D1-D3 are both decided and open |
| 30.6 | 1 | admitted 2026-11-15; spec pending | admitted (item 3) | none |
| 31.1-31.6 | 6 | registered; specs being written on `spec-plan31a` and `spec-plan31b`; approved on a ch-bsd MEH-only GO (L125) | admitted (item 4; 31.6 by Q30) | plan-31 says "five items" and "these four" |

### Standalone tasks and queue items {#table-standalone}

| task | n | real state (evidence) | disposition | stale status |
|---|---|---|---|---|
| release 0.84.0 (freeze item 1, written as 0.83.1) | 1 | merges `b11e5e5` and `62cafc9`; release `cab0a7d`; deployed `fb6e339`; live AC-6 recount 0 at `4c6a0c6` (L119) | done | freeze item 1 still reads "0.83.1: ship, deploy, recount" |
| `.venv-eval` duckdb 1.5.3 (store D5) | 1 | the venv imports 1.5.3 (read 2026-11-15) | done | freeze item 2: "then duckdb 1.5.3" |
| merge of the six spec branches | 1 | merged as they stand: `3be7676`, `327703d`, `e2010bd`, `b1be2e4`, `0a40f4b`, `88c2900` | done | none |
| bug-178, bug-179, bug-195, bug-216 | 4 | merged `76ec748`, `aea4098`, `102524d`, `7aed8df` | done | all four specs `approved` |
| T0 suite-trust sweep | 1 | spec merged `0e55687`; it is 29.4's body | admitted (item 2) | none |
| bug-185 | 1 | approved; revised on `spec-wave-t4`; unbuilt | admitted (item 5, T4) | none |
| bug-218 | 1 | approved on `spec-wave-t56` (L69, L74); R0 confirms the `suspected` row; R1-R7 need bug-185 merged | admitted (item 5) | no spec on master |
| G22 (`task-dq1-operational-content-out-of-graph`) | 1 | approved on `spec-wave-t56` (L74); depends only on bug-216 live, which is met | admitted (L128: after plan-30 release C) | no spec on master |
| G30 (`task-bug216-denotes-fold-evaluation`) | 1 | approved on `spec-wave-t3c`; a measurement | admitted (L128: folded into 30.6) | no spec on master |
| G32 (the m1 r2-lite confirm) | 1 | not run: the ledger holds only the DIRTY m1 round at `4b57796` | admitted (L128) | none |
| compaction-as-handoff | 1 | `drafting`; two approval blockers (queue review) | post-mod (named) | body says "queued right after 0.83.0" |
| agent-start-context | 1 | `drafting` | post-mod (named) | body says "queued after 0.83.0" |
| linked-readonly-store, with its usage measurement | 1 | `drafting`; "measure first" (queue review D2) | post-mod (named by L128) | body says "queued right after 0.83.0" |
| `legs_ms` timing pair (memory review D2) | 1 | no spec and no owner | post-mod (named by L128) | none |
| cross-partition `rel:` probe (memory review D3) | 1 | no spec and no owner | admitted (L128) | none |

## The mod's start condition {#mod-start}

Read from [[plan-24-mod-transport]] (its `depends-on` edge, [[plan-24-mod-transport#phasing]],
[[plan-24-mod-transport#decisions]]) and from each task spec's header. {#mod-start-lead}

### Each dependency against reality {#mod-deps}

| dependency, and where plan-24 states it | reality | class |
|---|---|---|
| task 3.7 merged (the plan's `depends-on` edge; `#phase-build`; the 24.2a, 24.2 and 24.4 headers) | merged `91ddbe0`; 0.81.0 | **met** |
| 23.0's sandbox and 21.1's events (task specs) | `d4bf001`; `535231e` | **met** |
| "spec r7 → approval" ([[pop-finished#override-2026-11-08]]) | r6 DIRTY, r7 fold unconfirmed; status `drafting` | **neither** |
| D1: hook-shaped work is held and retargets to the mod | superseded by D-Q5. Verb-side logic builds on hooks now: 25.1 shipped; 25.2, 25.3, 10.3, 21.2, 21.4 are admitted | **inside the freeze** (they become rows of 24.8 R5) |
| D-Q5: plan-24 is re-planned after the charter decision | the charter decision (G18) follows plan-28, which is post-mod | decided by L128: the freshness revision is the freeze's last step |
| the amends notes on `#decisions` and `#phasing`, and the 24.8 R5 rows (L38, G27) | unwritten ([[plan-review-fable-2026-11-14-queue#st-6]]) | **neither** |
| 24.6 R4 calls 21.5 R1's one builder, `stm.tool_event_fields` | not in `src/`; it is 21.5 phase B, frozen until the charter decision (D-Q4) | decided by L128: 24.6 takes the builder |
| 24.6 needs 24.0's "before" window closed: a week of pre-mod hook cost data | 24.0 is unbuilt; it edits `src/` and the generated hook env | inside plan-24: its first task; the week passes while 24.1-24.5 build |
| the modules the specs name | 29.5 splits `cli.py` and `Store`; 29.3 converges the transport classifier that 24.4 twins; 30.4 adds the `ppr_rank` daemon op the prompt hook calls | **inside the freeze** (plan-29, plan-30) |
| probes still owed ([[plan-24-mod-transport#probes-consequences]] item 4; batch 2's "not tested" row; `skill.prompt` unknown) | the probes ran on Claude Code 2.1.304; this machine runs 2.1.325 | **neither** |

### Freshness {#mod-freshness}

Yes: plan-24 needs a freshness revision before it starts, and a ch-bsd round after it. The
reasons, each checked on `master`:

- **Age.** Nine of the ten task specs were last committed on 2026-10-20; 24.6 on 2026-11-13.
  They were written against a clone of the 3.7 branch, before 3.7 merged.
- **A superseded decision.** D1 and `#phase-held` still say the hook-shaped work is "kept as
  records, not built". The user reversed that on 2026-11-13 (D-Q5). `#phase-now` still says 24.0
  and 24.1 "start now".
- **Shipped since.** 25.1 (the per-prompt recall runs through the verb; `hook_budget`;
  `recall_pack`), bug-212 (one store-level write refusal; `verbs.local_write` gained `create=`),
  bug-216, plan-26's memory layout, and 0.84.0's scan-prompt order and composite marker. 24.2a
  ("every hook path the mod takes over becomes a verb") describes the hook paths as they were at
  0.80. 24.6's later revisions (r5-r7) touched only tool observation.
- **Still to move.** Plan-29 turns `cli.py` into a package and `Store` into mixins. Plan-30
  release C moves the prompt hook's ranking into a daemon op. A revision written before those
  land is revised twice.
- **24.8 R5's table is short.** It lists 16.1-16.6, 19.5, 19.6 and 21.2-21.4. It now also owes
  rows for plan-10, 25.1-25.3, 25.1b, compaction-as-handoff, agent-start-context, the
  [[plan-of-plans#post-mod]] entries and [[design-note-tool-keyed-context-2026-11-15]].
- **One duplicate to settle.** 24.1's `.refmatrix/identity.json` and the linked store's R5 are
  two version records for one fact ([[plan-review-fable-2026-11-14-queue#dup-2]]). {#mod-freshness-list}

### What starts it {#mod-start-rule}

In order: the freeze list completes; the plan-24 freshness revision is written on the
post-plan-29, post-plan-30 tree (ch-architect on Fable); ch-bsd spec rounds run to MEH-only;
the lead rules; the user decides what is left; plan-24 is set `approved`; 24.0 and 24.1 start.
L128 made that revision the freeze's last step, and L129 put the re-evaluation of the post-mod
items after the mod's initial work. The amends notes can be written now. {#mod-start-rule-body}

## Post-mod by the freeze rule {#post-mod-rule}

The first version of this file listed 19 task ids that nothing admitted and no list named. L128
decided all of them: G22, G30, G32 and the cross-partition `rel:` probe are admitted, and the
rest are now named on [[plan-of-plans#post-mod]]. Two groups remain post-mod by the rule alone:
plan-8's deferral rows 43 and 44 (held with 19.2) and the registry backlog that 29.1 triages
(`pop-rewrite-draft` (applied to [[plan-of-plans]] 2026-11-15)). {#post-mod-rule-lead}

## The bookkeeping list {#bookkeeping}

The stale file statuses and their exact edits were re-read at `ad5df99` and are carried in
`pop-rewrite-draft` (applied to [[plan-of-plans]] 2026-11-15), so that the list survives this file's archive. The spec
merges already applied four of the edits first listed here (25.4 and 25.5 `superseded`; the
plan-10 task files; plan-28's files). {#bookkeeping-lead}

## The critical path to mod start {#critical-path}

The ordered list, with its lanes, waits and user gates, is `pop-rewrite-draft` (applied to [[plan-of-plans]] 2026-11-15). In
short: {#critical-path-lead}

1. 29.4 stages 2-5, with T0.6 in the measurement lane and plan-31's independent items beside
   them.
2. 29.1, then 29.5 alone, then 29.3 ∥ 29.2, 29.4f and 29.6.
3. 31.2; plan-30 (three releases), then G22, then 30.6 with G30; T2 as a second track, after
   the `rel:` probe.
4. G32; the hook-side items kept (10.3, 25.2, 25.3); T4, then bug-218.
5. After 31.5's cut: 21.2 → 21.4; 21.5 phase M.
6. The plan-24 freshness revision, to approval; then 24.0 ∥ 24.1.

The planning lane runs no tests and never waits. The test lane is one test process at a time.
The specs are on `master` as they stand (the user: "although they are stale, they should be
actionable still"), so there is no freshness revision per track: the RED author reconciles a
stale citation first (`pop-rewrite-draft` (applied to [[plan-of-plans]] 2026-11-15)). {#critical-path-body}

## Flags {#flags}

**Open.** One contradiction between the layers is left
(`pop-rewrite-draft` (applied to [[plan-of-plans]] 2026-11-15)): {#flags-open}

- **F5.** The freeze line says "22.6 R4 folded into 31.2". The 22.6 spec says "R4 (the sync edit
  fix) needs only 16.6's Wave-1 slice and may land first", and the rows R4 keeps include "its
  sidecar rows". The post-mod list says "23.4, the 16.6 slice and plan-17". 31.2's spec, in
  flight, must state R4 without the sidecar or name the slice as a dependency.

No dependency of plan-24's start is left that is neither met nor admitted. Plan-24's own text
still contradicts the decisions (D1 in force; 24.0 and 24.1 "start now"; the hook-shaped specs
"kept as records, not built"); the freshness revision corrects it. {#flags-p24}

**Answered on 2026-11-15** (Q32-Q36 = a; L128, L129): plan-10's dedupe against the post-mod
25.1b; G22 and G30, kept by the first triage's table and dropped by its summary; G32, on which
25.2 and 21.5 phase M wait; the `rel:` probe, on which 26.5 waits; the plan-24 re-plan waiting on
a post-mod charter decision; 24.6's builder inside 21.5's frozen phase; plan-24's missing
approval step. {#flags-answered}

**Fixed in compilation, not flags** (the later source wins): freeze item 1 names 0.83.1, which
L119 replaced with 0.84.0; item 2 reads "29.1 → 29.4", which L118 reordered, and lists a duckdb
upgrade that is done; L106 placed the `legs_ms` pair before 29.5, and 29.5 R0 item 10 lets it be
"explicitly held"; the queue review put bug-218 ahead of bug-185, on which its spec depends.
{#flags-fixed}
