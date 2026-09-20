---
gmd: "0.1"
id: task-13.4-include-sessions-policy
title: "Task 13.4: decide what include_sessions defaults to, on 13.0's numbers"
tags: [task, plan-13, sessions, policy, context]
metadata:
  node_type: task
  status: pending
  plan: plan-13-cross-partition-sweep
---

# Task 13.4: the include_sessions default {#root}

> Plan: [[plan-13-cross-partition-sweep]]
> Status: Pending
> Depends on: [[task-13.0-two-partition-kill-shot]]

rel: part-of -> [[plan-13-cross-partition-sweep]]
rel: depends-on -> [[task-13.0-two-partition-kill-shot]]
rel: derives-from -> [[bsd-plan13-cross-partition-sweep-0cb8b1a]]

## Requirements {#requirements}

- The audit's #b-4 established that the session substrate SHIPS: `session_ingest.py` writes
  turn-level cards into `sessions-<project>`, `rmx session recall|show|list|stats` read them, and
  the maintenance path ingests them. What gates them out of `rmx context` is one default-false
  boolean — `context.py:346`, `if not include_sessions and _is_session_card(ent.name): continue`,
  whose comment gives the reason: session cards would drown out specs, code and ADRs.
- So this task is NOT "build the session leg". It is: **decide, on 13.0's measured numbers, which
  surfaces should default `include_sessions` true**, and whether that alone captures the gain the
  sweep would deliver.
- The decision is recorded with its evidence, in `docs/PERFORMANCE.md` and as an ADR if the default
  changes — a default flip on a retrieval surface is an architectural decision, not a tweak.
- **This task may conclude that the sweep is unnecessary.** If 13.0's gain is carried entirely by
  the session leg and flipping the default captures it, that is the cheap answer and the plan says
  so ([[plan-13-cross-partition-sweep#open]]).
- Whatever is decided must not reintroduce the drowning-out the comment warns about: if the default
  flips, the session cards' share of the returned set is CAPPED and the cap is measured, not
  assumed.

## The evidence cannot come from arm P {#mixed-corpus}

`context._rank_entries` (`context.py:1237`) demotes session cards below durable documents even when
they are opted back in. On [[task-13.0-two-partition-kill-shot]]'s arm P **every** document is a
session card, so that sort key is constant and the demotion is a no-op (r2 #m-7). Arm P measures a
flag flip on a HOMOGENEOUS corpus; this task's question is about a MIXED one — this repo's store,
where 66 session cards compete with its docs and 366 memory rows. The numbers that decide the
default come from that store, and arm P's recovery delta is context, not evidence. {#mixed-lead}

## Acceptance criteria {#acceptance}

- A recommendation per surface (`context`, `scan-prompt`, `memory recall`), each with the measured
  hit@20 / MRR@20 delta from 13.0 and the measured share of returned rows that become session
  cards.
- If any default flips: the drown-out guard is a test — a query whose answer is an ADR still returns
  that ADR above session chatter on the fixture store.
- If no default flips: the reason is recorded, and 13.6's adoption question inherits it.

## Files {#files}

- modify `src/refmatrix/context.py` only if the decision is to flip a default
- modify `docs/PERFORMANCE.md` (the decision + evidence)
- create `docs/adr/00NN-session-partition-visibility.md` if a default changes
- create `tests/test_include_sessions_policy.py`

## Test strategy (RED first) {#test-strategy}

1. `test_session_cards_are_excluded_by_default_today` — characterization, pinning current behaviour
   before touching it.
2. `test_include_sessions_true_returns_session_cards` — the flag works as the plan claims (verify,
   do not assume).
3. `test_an_adr_answer_outranks_session_chatter_when_sessions_are_included` — the drown-out guard.
4. `test_session_share_of_the_returned_set_is_capped` — only if a default flips.

**Mutations:** invert the default without the cap (kills 3); remove the cap (kills 4).
