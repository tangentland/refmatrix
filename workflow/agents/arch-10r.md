---
gmd: "0.1"
id: agent-brief-arch-10r
title: "Brief: arch-10r — plan-10 revived: rewrite 10.2/10.3 on today's delivery stream, add 10.4 (no per-prompt injection on non-human prompts)"
tags: [agent-brief, dispatch, plan-10]
---

# Brief: arch-10r — plan-10 revived {#root}

Revise plan-10 and its task specs. Spec text only; no `src/`, no tests. A ch-bsd spec review
follows before approval.

rel: depends-on -> [[measurement-injection-already-held-2026-11-13]]
rel: depends-on -> [[agent-brief-green-251#hard-rules]]

## User decisions (2026-11-13) {#decisions}

The user accepted the lead's recommendations after the already-held measurement:
1. **Degrade, never suppress:** a re-delivered item is rendered as a one-line pointer (name,
   address, "shown turn N"), never dropped. This is plan-10's original non-negotiable
   ([[plan-10-injection-dedup#degrade]]); the measurement's cost check (6 of 13 labelled used items
   were re-deliveries) is why suppression stays banned.
2. **No per-prompt injection on non-human prompts:** scan-prompt and the per-prompt recall inject
   nothing on teammate / agent / cross-session / bus / task-notification turns.

## Evidence {#evidence}

`workflow/measurements/injection-already-held-2026-11-13.md` (provisional; ch-bsd pending):
48.0% of delivered items already held by the session, 46.7% by re-delivery alone; 64% of
prompt-channel deliveries ride non-human prompts (held 54-60% there; human prompts 27.7% /
40.4%); repeats are spread over the session (2,293 come back after ≥ 11 prompts; 555 items
delivered ≥ 21 times); compaction-aware 42.1%. Task 10.1's old measurement
(`workflow/measurements/injection-overlap.md`) asked a narrower question and stays as history.

## Do {#do}

1. **plan-10** (`workflow/plans/plan-10-injection-dedup.md`): status line and Decisions Log rows
   for the 2026-11-13 reopening (Q1 re-measured against the session; the two user decisions);
   task table with 10.2, 10.3 revived and 10.4 new; keep the execution contract (no suppression path
   may exist, even behind a flag; live re-measure before/after).
2. **10.2 rewritten** (degraded rendering): the LEDGER is the existing delivery record — 21.1's
   `delivered_in_session` / `recall-events.jsonl` `delivered` events (key = (scope, entity id), else
   name) — not a new store (prefer existing infra). The pointer line is rendered inside 25.1's pack
   (`recall_pack.py`, `hook_budget.py`; 25.1 is GREEN on branch `task-25.1-recall-hook-byte-budget`,
   clone `/Volumes/littlebig/refmatrix-plan25-1`, merges after 26.4) and in scan-prompt's renderer.
   A degraded item still emits a `delivered` event, marked `degraded`, so 21.5 / the next
   measurement can count it. Byte saving is reported. Read 25.1's spec rev 7 first; say exactly
   which 25.1 surfaces 10.2 changes and sequence it after 25.1's merge.
3. **10.3 rewritten** (resets): an item re-promotes to full after the session's last compaction
   (PreCompact / SessionStart `compact|clear` — 25.1 R11 already owns that entry) and after a turn
   TTL N (pick N from the measurement's gap distribution and say why). No second decay mechanism
   (helix primitive reused).
4. **10.4 new** (non-human prompt gate): one predicate, extending `stm.is_ambient_text` (today:
   `<channel`, `<task-notification`, `[SYSTEM NOTIFICATION`) to the turn shapes Claude Code
   delivers for teammate, agent and cross-session messages — establish the exact prefixes from
   real transcripts (read-only, counts and prefixes only, never message text). The gate sits beside
   25.2's ack-only gate in the verb (25.2 is pending, depends on 25.1): decide whether 10.4 extends
   25.2 or lands as its own predicate called at the same point, and record the sequencing. Counted
   and said: a gated prompt logs a `skipped_non_human` row, never a silent skip.
5. Each task: requirements, ACs with killing mutations (suppression must be impossible: a test
   proves no code path drops a re-delivered item), files to modify, a before/after re-measure on
   the same corpus.

## Where {#where}

Edit on dev master `/Users/tholley/claude_tools/refmatrix` is NOT allowed for agents — work in a
fresh clone: `git clone -q /Users/tholley/claude_tools/refmatrix /Volumes/littlebig/refmatrix-plan10`,
branch `task-plan10-revival`, symlink `.venv-eval` to the dev one (never stage it). Commit by
pathspec. GMD lint 0 errors on every file touched (`python3 tools/gmd/lint.py <path>`). Never
search from `/`. Text report: shas, the decisions you made "as the user would" with reasons, open
questions for the user.

## Amendments after dispatch (2026-11-13) {#amendments}

1. Q7: the dedupe is NOT a per-item pointer — first re-planned onto 19.6 R5/R6 (rev 2 `308edc8`,
   provisional NO-GO `1e4c6bb`).
2. Suppression reopened (degrade-only no longer non-negotiable); user words paraphrased tersely, cited
   by Q-id (Q1).
3. Q9 = curator status silent on non-human turns (10.4b); lead decisions: agent-message turns are not
   focus turns; an envelope origin field is read before the prefix.
4. 10.4 gets a with/without comparison (offline: dd-10r; live A/B nested with the handhold
   experiment). Rev 3 `ff8ca4d`: policy table, A/B, curator entry.
5. Q11 = 4+3, Q12 = replay first; four held-modelling rules accepted.
6. FINAL: Q13 = names-only (design 3) now, 4+3b a future A/B arm; Q10 = no separate non-human gate,
   same dedupe; 10.5 = the replay (passed) + the 50-probe read-back still to run.
7. Add 10.6 injection presentation (kind labels, generic headers replaced, STM composite via 19.6
   R5 `unchanged`); 10.4b curator prints only on change.
