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

Every question the lead asks the user gets a stable id here (`Q-<n>`, never reused) before it is
asked. Each reply that asks anything ends with the ids still open. The user answers by id
("Q-3: b") at any time; an unqualified "yes" answers only the single question it follows, and
when several are open the lead asks which. An answer the lead had to INTERPRET is recorded as
`assumed` and stays open until confirmed. Answered rows keep the user's answer and what was done.

Established 2026-11-13 after the user: asked for a running ledger of questions after an ambiguous answer

rel: related-to -> [[plan-of-plans]]

The session handoff (`handoff.md` `#open`) points here instead of keeping its own question list.

## Open {#open}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|

## Answered {#answered}

| id | asked | question | answer | acted |
|---|---|---|---|---|
| Q-1 | 2026-11-13 | Verbatim user prompts in today's docs, before the push to the public repo | a: paraphrase before the push | today's docs paraphrased (see the commit) |
| Q-2 | 2026-11-13 | Remove the `CLAUDE.md` ignore line fleet-wide after bug-216 deploys? | a: fleet-wide after deploy | recorded in task-bug216 `#fleet`; done at deploy, announced |
| Q-3 | 2026-11-13 | Handhold experiment primary outcome: orientation cost after `/clear` or a new session? | b: said both triggers are relevant and effectively the same measure | one measure, two triggers (session start and `/clear`) |
| Q-4 | 2026-11-13 | Handhold experiment arm B: opt-in or randomised? | b: randomise for a fixed period | exploration `#assignment` updated |
| Q-5 | 2026-11-13 | Handhold experiment projects | a: refmatrix + cliquedb | exploration updated |
| Q-6 | 2026-11-13 | "Used without being named" as its own task beside 19.6's transcript scorer? | a: yes, draft the task row | task 21.7 drafted (plan-21) |
| Q-7 | 2026-11-13 | Confirm plan-10 dedupe = per-item pointer + non-human gate | b: pointed to the context-diff mechanism as better than a per-item pointer | correct: 19.6's versioned injection (R5 unchanged-lines, R6 keyframe + delta) is the dedupe; `arch-10r` re-planning plan-10 onto it; the non-human gate (10.4) stands |
| Q-8 | 2026-11-13 | Confirm bug-216 = resolver fix + `denotes` link | a: confirmed | spec rev 3-4 stand |
| Q-0a | 2026-11-13 | bug-214: untrack the live store files in cliquet, atldb, prep_prolific? | chose to untrack and ignore the store files | untracked + ignored on the checked-out branches |
| Q-0b | 2026-11-13 | 21.5 OD-4 (19.6's scorer calls `tool_touches`) | "agree" | decision row d21-5a |
| Q-0c | 2026-11-13 | 21.5 OD-5 (W = 2) | a decaying score, plateau to lag 3 ("3 or 4") | kernel k = 3, h = 2; k = 4 sensitivity row |
| Q-0d | 2026-11-13 | AC-15 may copy cliquedb's store read-only? | allowed the read-only cliquedb copy | `#ofu-cliquedb` closed |
| Q-0e | 2026-11-13 | Pilot the R12 labels before building 21.5? | chose the labelled pilot first without withdrawing the approval track | `lbl-215` pilot; approval track kept |
| Q-0f | 2026-11-13 | Measure the three clique sources before deciding? | yes | `tc-215` phases 1-3 |
| Q-0g | 2026-11-13 | Add the handhold outcome exploration? | asked for the exploration to be added | `exploration-handhold-outcome-experiment` |
| Q-0h | 2026-11-13 | Fix bug-216? | asked for bug-216 to be fixed | spec + `red-216` |
| Q-0i | 2026-11-13 | Measure the already-held share of injections? | yes | `dd-10r`; 48.0% |
| Q-0j | 2026-11-13 | plan-10's "degrade, never suppress" | "can be reopened" | sent to `arch-10r` (tiered policy, pre-registered gate) |
