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

Next id: **Q15**.

### Open {#open}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q14 | 2026-11-13 | How should hook output live within the 9.5k hard limit (25.1 rev 8)? Options: clamp; rank-and-pack (today); degrade ladder (full → lead excerpt → pointer → names line); one budget across producers; spill to a pull page; defer; shrink at source. | (a) degrade ladder + spill-to-pull, clamp as a counted safety net; (b) clamp only (rev 8 as written); (c) another combination | open |

### Answered {#answered}

| id | asked | question | answer | acted |
|---|---|---|---|---|
| Q13 | 2026-11-13 | Dedupe design after the replay rejected 4+3 | a: names-only (design 3) now; 4+3b later as a live A/B arm | `arch-10r` re-specs 10.2 as names-only; 4+3b recorded as a future A/B arm |
| Q10 | 2026-11-13 | Non-human turns | a: no separate gate — same dedupe as human prompts | 10.4 keeps the focus-graph change and curator silence (Q9); its injection gate is dropped |
| Q11 | 2026-11-13 | plan-10 dedupe design for the per-prompt payloads (seven options) | 4+3: rank new items first, collapse held ones into one 'still in play' names line | `arch-10r` re-specs 10.2 on it after the replay; 19.6 block diff not used for these payloads |
| Q12 | 2026-11-13 | How to choose among the Q11 designs? | a: replay-score 1 / 3 / 4+3 / 5 first | `dd-10r` replay, pre-registered; also scores Q10's non-human policies (none / 4+3 / full) |
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
