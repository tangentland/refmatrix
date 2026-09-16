---
gmd: "0.1"
id: plan-10-injection-dedup
title: "scan-prompt stops re-paying for context the turn already has"
tags: [plan, scan-prompt, context, helix, hooks]
metadata:
  node_type: plan
  status: completed
  created: 2026-09-15
---

# Proposed Plan: scan-prompt degrades repeats instead of re-sending them {#root}

**Date:** 2026-09-15
**Status:** COMPLETED as a negative result. 10.1 ran and returned median carried **0.000** against a
pre-registered 0.40; 10.2 and 10.3 are NOT built. Full measurement: `workflow/review-output/injection-overlap.md`.
**Location:** `workflow/plans/plan-10-injection-dedup.md` — permanent home; stage is `metadata.status`.

rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: depends-on -> [[plan-9-context-cost-telemetry]]
rel: derives-from -> [[project_helix_phase1_shipped]]
rel: reinforces -> [[feedback_prefer_existing_infra]]
rel: related-to -> [[project_stm_composite_and_focus_rebuild]]
rel: contradicts -> [[project_helix_log_confounded]]
rel: specifies -> [[task-10.1-plan-10-injection-dedup]]
rel: specifies -> [[task-10.2-plan-10-injection-dedup]]
rel: specifies -> [[task-10.3-plan-10-injection-dedup]]

## Context {#context}

`scan-prompt` is the only rmx surface whose cost is unavoidable and recurring: it fires on every
`UserPromptSubmit`, and the agent cannot decline to pay it. Over a long session the same
neighbourhood — the same `daemon.py` entries, the same memory bodies — is plausibly re-injected
turn after turn, and the window is charged every time.

Plan 9 built the instrument that can see this (`out_bytes` per invocation) but cannot answer it
retroactively: `query.log` stores the query, never the RESULT. So the repeat rate is unknown, and
[[project_helix_log_confounded]] is this project's own record of what happens when a hook surface
is reasoned about instead of measured — a near-empty log almost decided a phase.

Hence the shape of this plan: **task 10.1 is an experiment with a pre-registered threshold, and
10.2/10.3 do not start unless it clears.**

## The failure mode this plan is designed around {#hazard}

The obvious implementation — remember what was sent, suppress it next time — is **unsafe**, and
unsafe in the worst way: silently.

The ledger records what was SENT. It cannot record what SURVIVES. Those diverge the moment
compaction runs:

> Turn 3 injects `daemon.py:2841 _op_ingest_path`. Turn 40 compaction drops it. Turn 41
> `scan-prompt` suppresses it as already-sent. **The model now has neither.**

No error, no log line — just quietly worse retrieval, the hardest class of defect to detect. It is
the [[impression_bsd_same_input_guard]] shape exactly: a guard whose state is not the state it is
guarding. A `UserPromptSubmit` hook cannot observe the context window.

**So this plan never suppresses.** See [[#degrade]].

## Proposed Approach {#proposed-approach}

### Degrade, never suppress {#degrade}

A repeat is emitted as a one-line pointer instead of a full entry:

```
first time:   daemon.py:2841  _op_ingest_path
              <KWIC snippet, 3-5 lines>

on repeat:    daemon.py:2841  _op_ingest_path   [shown turn 3]
```

That keeps roughly 80-90% of the saving while holding a correctness FLOOR: if the model lost the
snippet, it still has the address and can read the file. Suppression trades a bounded, known cost
for an unbounded, invisible one; degradation does not. This is the single non-negotiable design
constraint of the plan.

### The ledger, and clearing it {#ledger}

Per-session, per-entity `last_injected_turn`. Two independent resets, because neither is
trustworthy alone:

- **PreCompact** clears the ledger. rmx already owns that hook (`precompact_checkpoint`), so the
  state lives where the signal already arrives — no new mechanism ([[feedback_prefer_existing_infra]]).
- **A turn TTL** re-promotes an entry to full after N turns regardless. Claude Code has
  auto-compaction and context-editing paths that may never surface as a `PreCompact` this hook
  sees; a ledger that trusts one signal is a guard that cannot fire when it matters.

### This is helix, pointed at injection {#helix}

Per-entity last-seen time with an expiring suppression IS the helix primitive, applied to the
injection surface rather than to retrieval staleness. It does NOT get a second decay
implementation. [[feedback_reuse_shared_stoplist]] is the record of one bug appearing at four call
sites because each grew its own copy.

`stm` already maintains "a running aggregate of every prompt+result" per session, so the ledger
may belong there rather than in a new store — task 10.2 establishes which, and reuses rather than
adds.

## Open Questions {#open-questions}

### Q1: Does the repeat actually happen, and how much? {#q1}
**Status:** RESOLVED — NO.

**Measured 2026-09-15:** median carried **0.000**, mean 0.156, p75 0.100, over 187 pairs from 400
replayed real prompts. The median consecutive call shares zero entries with its predecessor. The
run was 187 pairs against a registered 200 and self-reported UNDERPOWERED; that limitation is kept
attached rather than laundered, and it does not bridge 0.00 to 0.40.

**Pre-registered threshold, fixed before the numbers are read:** median pairwise entry overlap
between CONSECUTIVE `scan-prompt` calls must be **>= 40%**, over at least 200 replayed real
prompts.

- **>= 40%** — build 10.2 and 10.3.
- **< 40%** — the plan stops at 10.1, the measurement is the deliverable, and the finding is
  recorded the way [[task-8.4-plan-8-derived-coverage-notes]] recorded its negative result.

40% is chosen because below it the median turn saves less than half of a surface that is already
the cheaper of the two context consumers plan 9 measured — not worth a correctness-sensitive
mechanism in the always-on path.

### Q2: Where does the ledger live? {#q2}
**Status:** OPEN, decided in 10.2. STM session state is the leading candidate precisely because it
already exists and is already per-session; a new sidecar file would be a second lifecycle to keep
correct across compaction.

### Q3: Is scan-prompt even the right target? {#q3}
**Status:** OPEN, and honestly unresolved. Plan 9 measured `grep` at 13,749 B mean against
`scan-prompt` near zero — but on a THROWAWAY store with a tiny corpus, and `grep` fires when the
agent chooses while `scan-prompt` fires always. Frequency may invert the ranking. Task 10.1
reports both surfaces' live per-prompt cost so this is answered with the same run.

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Repeat rate | Pre-registered >= 0.40. **Measured 0.000.** Plan stops at 10.1. | 2026-09-15 |
| Q2 | Ledger location | Moot — not built. | 2026-09-15 |
| Q3 | scan-prompt vs grep | Moot for dedup. Separate finding: 28% of scan-prompt calls return nothing. | 2026-09-15 |
| Q2 | Ledger location | Deferred to 10.2; reuse STM session state if it fits. | — |
| Q3 | scan-prompt vs grep priority | 10.1 reports both live. | — |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 10.1 | **Measure the overlap** — replay real prompts, report against the Q1 threshold | plan 9 |
| 10.2 | ~~Ledger + degraded rendering~~ — **NOT BUILT**, 10.1 did not clear | 10.1 |
| 10.3 | ~~PreCompact clear + turn TTL~~ — **NOT BUILT** | 10.2 |

## Execution contract {#execution}

TDD per [[tdd-governance]]. Plan-specific gates:

- **10.1 is pre-registered.** The threshold above is fixed. A result below it ships as a negative
  finding; it does not get a lowered bar ([[project_helix_phase2_decision_criterion]]).
- **No suppression path may exist in the code**, not even behind a flag. A dead flag is dead code
  and self-concealing ([[impression_bsd_dead_flag_surface]]); the degraded line is the only repeat
  behaviour.
- **The saving is re-measured live**, with `rmx telemetry --context` before and after, on the same
  corpus, after the fleet has been busy — not in the quiet window
  ([[impression_bsd_cost_measured_idle]]).
