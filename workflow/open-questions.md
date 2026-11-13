---
gmd: "0.1"
id: open-questions
title: "Open questions for the user — the running ledger"
tags: [workflow, questions, decisions, user]
metadata:
  node_type: ledger
  created: 2026-11-13
---

# Open questions for the user {#root}

Every question the lead asks the user gets an id here before it is asked: `Q<n>`, a simple counter
that starts at 1 in each session and increments by one, never reused within the session (user,
2026-11-13). Rows are grouped by session, so `(session, Q<n>)` is unique across sessions. A question is shown
with its id the first time it is asked (`**Q9** — <question>`); later mentions use the id. Each reply that asks anything ends with the ids still open. The user answers by id
("Q3: b") at any time; an unqualified "yes" answers only the single question it follows, and
when several are open the lead asks which. An answer the lead had to INTERPRET is recorded as
`assumed` and stays open until confirmed. Answered rows keep the user's answer and what was done.

Established 2026-11-13 after the user: track questions by id

rel: related-to -> [[plan-of-plans]]

The session handoff (`handoff.md` `#open`) points here instead of keeping its own question list.

## Session f0521bff (2026-11-13) {#session-f0521bff}

Next id: **Q13**.

### Open {#open}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q10 | 2026-11-13 | Non-human gate (10.4): with the gate 62% of prompt-channel injections go, 0 labelled uses lost, 10 explicit R12 uses (2 near-term) rode agent-message turns with no other delivery — rule trips. Now a single policy table in 10.4 (none / delta / full per family and surface); a live A/B (arms nested in the handhold experiment, ≥14 days, ≥40 sessions/arm/store, bands pre-written) follows ship. | (b) full gate (none for every family), shipped inside the live A/B; (c) none for task-notifications only, full for agent messages; (a) delta on non-human turns — needs 10.2's block state even if Q11 says no 10.2, and that state holds little, so it cuts far less than 57.5% | on hold — user: wait for Q11 |
| Q11 | 2026-11-13 | plan-10 dedupe of the per-prompt payloads. 19.6's block diff fails there (lists change every turn). User asked for design options; seven laid out (pointer, suppress+refresh, names-only line, rank-by-novelty, item diff+keyframe, session-aware retrieval, pull-only). | lead recommends 4+3: rank new items first, collapse held ones into one 'still in play' line — pending Q12 | open (options given) |
| Q12 | 2026-11-13 | How to choose among the Q11 designs? | (a) replay-score 1 / 3 / 4+3 / 5 on the same sessions (bytes saved, new items gained, labelled + explicit uses kept visible), then decide; (b) go straight to 4+3; (c) pick another | open |

### Answered {#answered}

| id | asked | question | answer | acted |
|---|---|---|---|---|
| Q9 | 2026-11-13 | `rmx curator status` silent on non-human turns too? | a: yes, follow-on to 10.4 | sent to `arch-10r`: a 10.4 follow-on plumbs the envelope into `curator status` |
| Q1 | 2026-11-13 | Verbatim user prompts in today's docs, before the push to the public repo | a: paraphrase before the push | today's docs paraphrased (see the commit) |
| Q2 | 2026-11-13 | Remove the `CLAUDE.md` ignore line fleet-wide after bug-216 deploys? | a: fleet-wide after deploy | recorded in task-bug216 `#fleet`; done at deploy, announced |
| Q3 | 2026-11-13 | Handhold experiment primary outcome: orientation cost after `/clear` or a new session? | b: both; same measure | one measure, two triggers (session start and `/clear`) |
| Q4 | 2026-11-13 | Handhold experiment arm B: opt-in or randomised? | b: randomise for a fixed period | exploration `#assignment` updated |
| Q5 | 2026-11-13 | Handhold experiment projects | a: refmatrix + cliquedb | exploration updated |
| Q6 | 2026-11-13 | "Used without being named" as its own task beside 19.6's transcript scorer? | a: yes, draft the task row | task 21.7 drafted (plan-21) |
| Q7 | 2026-11-13 | Confirm plan-10 dedupe = per-item pointer + non-human gate | b: context diff over pointer | correct: 19.6's versioned injection (R5 unchanged-lines, R6 keyframe + delta) is the dedupe; `arch-10r` re-planning plan-10 onto it; the non-human gate (10.4) stands |
| Q8 | 2026-11-13 | Confirm bug-216 = resolver fix + `denotes` link | a: confirmed | spec rev 3-4 stand |

### Decided before the ledger existed (no id) {#pre-ledger}

| id | asked | question | answer | acted |
|---|---|---|---|---|
| — | 2026-11-13 | bug-214: untrack the live store files in cliquet, atldb, prep_prolific? | untrack + ignore | untracked + ignored on the checked-out branches |
| — | 2026-11-13 | 21.5 OD-4 (19.6's scorer calls `tool_touches`) | "agree" | decision row d21-5a |
| — | 2026-11-13 | 21.5 OD-5 (W = 2) | a decaying score, plateau to lag 3 ("3 or 4") | kernel k = 3, h = 2; k = 4 sensitivity row |
| — | 2026-11-13 | AC-15 may copy cliquedb's store read-only? | cliquedb copy allowed | `#ofu-cliquedb` closed |
| — | 2026-11-13 | Pilot the R12 labels before building 21.5? | pilot first, approval track kept | `lbl-215` pilot; approval track kept |
| — | 2026-11-13 | Measure the three clique sources before deciding? | yes | `tc-215` phases 1-3 |
| — | 2026-11-13 | Add the handhold outcome exploration? | asked for the exploration | `exploration-handhold-outcome-experiment` |
| — | 2026-11-13 | Fix bug-216? | fix bug-216 | spec + `red-216` |
| — | 2026-11-13 | Measure the already-held share of injections? | yes | `dd-10r`; 48.0% |
| — | 2026-11-13 | plan-10's "degrade, never suppress" | "can be reopened" | sent to `arch-10r` (tiered policy, pre-registered gate) |
