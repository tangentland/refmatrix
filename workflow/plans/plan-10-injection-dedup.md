---
gmd: "0.1"
id: plan-10-injection-dedup
title: "Injected context the session already holds is degraded to a pointer, never dropped; non-human prompts get no per-prompt injection"
tags: [plan, scan-prompt, memory-recall, context, helix, hooks, injection, dedupe]
metadata:
  node_type: plan
  status: drafting
  created: 2026-09-15
  updated: 2026-11-13
---

# Proposed Plan: degrade repeats instead of re-sending them; inject nothing on non-human prompts {#root}

**Date:** 2026-09-15; reopened 2026-11-13.
**Status:** DRAFTING (reopened). 10.1 (2026-09-15) measured consecutive-call overlap at median
**0.000** and stopped the plan; that result stands as history. On 2026-11-13 the user asked whether
injected context is deduped against what the session already holds (it is not), and the
re-measurement ([[measurement-injection-already-held-2026-11-13]], provisional until ch-bsd) found
**48.0%** of delivered items already held, almost all by re-delivery, and **64%** of prompt-channel
deliveries riding non-human prompts. The user accepted two decisions ([[#decisions-log]] rows
D1, D2). 10.2 and 10.3 are revived and rewritten on today's delivery stream; 10.4 is new. The specs
go through a ch-bsd spec review before this plan moves to `approved`.
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
rel: specifies -> [[task-10.4-non-human-prompt-gate]]
rel: derives-from -> [[measurement-injection-already-held-2026-11-13]]
rel: depends-on -> [[task-25.1-recall-hook-byte-budget]]
rel: depends-on -> [[task-25.2-thin-prompt-gate]]
rel: depends-on -> [[task-21.1-context-usage-telemetry]]
rel: related-to -> [[task-19.6-phased-context-and-topic-cache]]
rel: related-to -> [[task-21.5-tool-used-signal]]

## Context {#context}

`scan-prompt` and the per-prompt recall are the rmx surfaces whose cost is unavoidable and
recurring: they fire on every `UserPromptSubmit`, and the agent cannot decline to pay them. Over a
long session the same neighbourhood — the same `daemon.py` entries, the same memory bodies — is
re-injected turn after turn, and the window is charged every time.

In 2026-09 nothing could see this: `query.log` stored the query, never the result. 21.1 (released
0.80.0) added the `delivered` event per named item with its byte span (`recall-events.jsonl`), so
the question is now answered from the log instead of reasoned about
([[project_helix_log_confounded]] is this project's record of what reasoning costs here).

**2026-11-13 numbers** ([[measurement-injection-already-held-2026-11-13#result]]): 7,641 of
15,934 delivered units (48.0%; 46.9% of item bytes) were already held by the session when
delivered; re-delivery alone is 46.7%, and restricted to hook channels 43.2% / 51.9% (refmatrix /
cliquedb); the compaction-aware variant is 42.1%. Repeats are spread across the session (2,293
come back after 11 or more prompts; 555 items were delivered 21 or more times), on different words
(the item's name is in both prompts in 1.9%). About 64% of prompt-channel units rode non-human
prompts (teammate / agent / task-notification turns). {#context-2026-11-13}

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

The 2026-11-13 cost check makes the hazard concrete: 6 of 13 labelled CAUSED+INFORMED used items
were re-deliveries ([[measurement-injection-already-held-2026-11-13#cost]]). Suppression would have
removed items the agent then used.

**So this plan never suppresses.** See [[#degrade]].

## Proposed Approach {#proposed-approach}

### Degrade, never suppress {#degrade}

A repeat is emitted as a one-line pointer instead of a full entry:

```
first time:   daemon.py:2841  _op_ingest_path
              <KWIC snippet, 3-5 lines>

on repeat:    _op_ingest_path  [code]  daemon.py:2841  [shown turn 3]
```

The pointer keeps the address, so if the model lost the snippet it can still read the file. That
is a correctness FLOOR. Suppression trades a bounded, known cost for an unbounded, invisible one;
degradation does not. This is the single non-negotiable design constraint of the plan (user
decision D1, 2026-11-13).

### The ledger is the delivery log {#ledger}

The ledger is NOT a new store. It is 21.1's `delivered` events in `recall-events.jsonl`, read by
the existing backwards reader `telemetry.delivered_in_session` ([[task-10.2-plan-10-injection-dedup#r2]]).
Q2's 2026-09 leading candidate (STM session state) predates that log; the log already holds the
session, the turn, the item key and the byte span of every delivery, so a second record would be a
second lifecycle to keep correct ([[feedback_prefer_existing_infra]]).

An item is **held** when, in the same session, it was delivered IN FULL on a hook channel after
the session's last compaction marker and within a turn window. Two resets, because neither is
trustworthy alone:

- **The compaction marker** ([[task-10.3-plan-10-injection-dedup]]): written on PreCompact and on
  SessionStart `compact|clear`, the same marker task 19.6 R8a names
  ([[task-19.6-phased-context-and-topic-cache]]). After it nothing is held.
- **The turn window** ([[task-10.2-plan-10-injection-dedup#r4]]): an item last shown in full more
  than N = 10 turns ago renders full again. Claude Code has context-editing paths that may never
  surface as a hook this code sees; a ledger that trusts one signal is a guard that cannot fire
  when it matters.

### This is helix, pointed at injection {#helix}

Per-entity last-seen plus a window IS the helix primitive, applied to the injection surface rather
than to retrieval staleness. It does NOT get a second implementation: the window compare is ONE
function, `helix.in_window`, called by `helix.annotate` and by the ledger
([[task-10.2-plan-10-injection-dedup#r4]]). [[feedback_reuse_shared_stoplist]] is the record of one
bug appearing at four call sites because each grew its own copy. What is NOT reused is helix's
ring index: it records what the agent TOUCHED, and the ledger needs what was INJECTED.

### Non-human prompts get no per-prompt injection {#non-human}

User decision D2 (2026-11-13): scan-prompt and the per-prompt recall inject nothing on teammate,
agent, cross-session, bus or task-notification turns. One predicate decides what such a turn is
(`terms.ambient_family`, behind `stm.is_ambient_text`), and it is called through 25.2's one prompt
gate ([[task-10.4-non-human-prompt-gate]]). A gated call writes a `skipped_non_human` row; it is
never a silent skip.

## Open Questions {#open-questions}

### Q1: Does the repeat actually happen, and how much? {#q1}
**Status:** RESOLVED twice; the second answer governs.

- **2026-09-15 (10.1, history):** median consecutive-call overlap **0.000** against a
  pre-registered 0.40 over 187 pairs; the plan stopped. That measured CONSECUTIVE scan-prompt calls
  only and never compared an injection with what the session already held ([[injection-overlap]]).
- **2026-11-13 (re-measured against the session):** 48.0% held, band ≥ 30% → reopen
  ([[measurement-injection-already-held-2026-11-13#result-band]]). The cost check tripped (6 of 13
  used items were re-deliveries, Wilson 23-71%), so the action went to the user, who chose
  degrade-never-suppress (D1).

### Q2: Where does the ledger live? {#q2}
**Status:** RESOLVED 2026-11-13 — the delivery log (`recall-events.jsonl`), read by
`telemetry.delivered_in_session`; the compaction marker lives in STM session state. See [[#ledger]].

### Q3: Is scan-prompt even the right target? {#q3}
**Status:** RESOLVED 2026-11-13 — both prompt channels. scan_prompt held 42.2% / 45.6% and
prompt_recall 57.6% / 77.3% (refmatrix / cliquedb). 10.2 degrades both, and session_start.

### Q4: What is a non-human prompt, exactly? {#q4}
**Status:** RESOLVED 2026-11-13 by a read-only census of the hook envelope (STM ring `input`
events, `query.log` hook rows) and the transcripts, counts and prefixes only
([[task-10.4-non-human-prompt-gate#census]]). The hook's `prompt` for a teammate or agent message
to the main session starts `<agent-message from=`; cross-session messages `<cross-session-message`;
the existing three (`<channel`, `<task-notification`, `[SYSTEM NOTIFICATION`) stay.

## Decisions Log {#decisions-log}

| # | Question | Decision | Date |
|---|----------|----------|------|
| Q1 | Repeat rate (consecutive calls) | Pre-registered >= 0.40. **Measured 0.000.** Plan stopped at 10.1. | 2026-09-15 |
| Q2 | Ledger location | Moot — not built. | 2026-09-15 |
| Q3 | scan-prompt vs grep | Moot for dedup. Separate finding: 28% of scan-prompt calls return nothing. | 2026-09-15 |
| Q1' | Already-held share (against the session) | **48.0%** held, ≥ 30% band → reopen; cost check tripped → the user decides | 2026-11-13 |
| D1 | What a re-delivered item becomes (user) | **Degrade, never suppress**: a one-line pointer (name, address, "shown turn N"); no suppression path, not even behind a flag | 2026-11-13 |
| D2 | Non-human prompts (user) | **No per-prompt injection** on teammate / agent / cross-session / bus / task-notification turns; counted as `skipped_non_human` | 2026-11-13 |
| Q2' | Ledger location | 21.1's `delivered` events through `delivered_in_session`; key `(scope, entity_id)`, else `(scope, kind, name)`; hook channels only; full deliveries only | 2026-11-13 |
| Q3' | Which channels | scan_prompt, prompt_recall, session_start degrade; precompact and the agent-pulled channels never degrade | 2026-11-13 |
| Q4 | Non-human predicate | `terms.ambient_family`, seven harness openings, behind `stm.is_ambient_text`; called through 25.2's `terms.prompt_gate` | 2026-11-13 |
| P1 | Task split | the turn window moves INTO 10.2 (a ledger with no window must never exist on master, and no flag may stage it); 10.3 owns the compaction marker and the live re-measure | 2026-11-13 |

## Task Breakdown {#task-breakdown}

| Task ID | Title | Depends On |
|---------|-------|------------|
| 10.1 | **Measure the overlap** — consecutive-call replay against the Q1 threshold (complete; history) | plan 9 |
| 10.4 | **Non-human prompt gate** — one predicate through 25.2's gate; scan-prompt and the per-prompt recall inject nothing; `skipped_non_human` rows | 25.1, 25.2 merged |
| 10.2 | **Degraded rendering from the delivery log** — pointer lines in 25.1's pack and in scan-prompt's renderer, the turn window, `degraded` delivered events, the byte saving | 25.1 merged; 10.4 merged |
| 10.3 | **Compaction marker + live re-measure** — PreCompact and SessionStart `compact|clear` reset the ledger (19.6 R8a's marker), before/after on the same corpus | 10.2 |

**Order:** 25.1 → 25.2 → 10.4 → 10.2 → 10.3. 10.4 lands first because it removes the larger
share (non-human prompts) with no rendering change, and because it changes the STM turn unit the
window counts in (non-human turns stop being recorded as `input`), so 10.2's window is defined and
re-measured in one unit from its first commit. 10.2 and 10.3 SHOULD reach a release together; a
release between them is safe (10.2's window bounds a stale pointer to 10 turns) but not intended.
{#order}

## Execution contract {#execution}

TDD per [[tdd-governance]]. Plan-specific gates:

- **10.1 is pre-registered and closed.** Its negative result is history; it is not re-scored.
- **No suppression path may exist in the code**, not even behind a flag. A dead flag is dead code
  and self-concealing ([[impression_bsd_dead_flag_surface]]); the degraded line is the only repeat
  behaviour. Each task carries a property test that every item named without the ledger is named
  with it (full or as a pointer), and the mutations that try to drop one.
- **The saving is re-measured live**, with `rmx telemetry --context` before and after, on the same
  corpus, after the fleet has been busy — not in the quiet window
  ([[impression_bsd_cost_measured_idle]]). "Same corpus" also means an OFFLINE replay of the
  2026-11-13 corpus (refmatrix 2026-10-20..11-13, cliquedb 2026-11-04..11-11) through the GREEN
  functions, so the before/after differ only by the code.
- **Counts only.** Every measurement reads transcripts, rings and logs read-only and reports counts,
  bytes and harness prefixes, never prompt or message text ([[feedback_no_raw_prompts_in_public_repo]]).

## Revision 2026-11-13 (reopening) {#rev-2026-11-13}

Reopened by the lead after [[measurement-injection-already-held-2026-11-13]] on the user's two
decisions; specs rewritten by `arch-10r` (brief `workflow/agents/arch-10r.md`).

rel: derives-from -> [[agent-brief-arch-10r]]

| change | anchor |
|---|---|
| status `in-progress` → `drafting`; Q1 re-answered against the session; Q2-Q4 resolved | [[#root]], [[#open-questions]] |
| D1, D2 and the ledger / channel / predicate / split decisions logged | [[#decisions-log]] |
| 10.2, 10.3 rewritten; 10.4 added; order fixed | [[#task-breakdown]], [[#order]] |
| the ledger is the delivery log, the window is helix's one compare | [[#ledger]], [[#helix]] |
