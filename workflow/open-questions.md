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

Established 2026-11-13 after the user: "on my yes that is ambiguous, you need to keep a running
list of questions you ask me ... we need a way to track my responses to questions not yet
answered."

rel: related-to -> [[plan-of-plans]]

The session handoff (`handoff.md` `#open`) points here instead of keeping its own question list.

## Open {#open}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|
| Q-1 | 2026-11-13 | Today's docs quote the user's prompts verbatim as provenance (four 21.5 measurements, the handhold exploration, the 25.1 rev-7, bug-216 and dd-10r docs); master pushes to the PUBLIC `tangentland/refmatrix`. The memory rule says raw prompts never go into the public repo. | (a) paraphrase before the push; (b) keep them as decision records (the repo already quotes user decisions in plan docs) | open |
| Q-2 | 2026-11-13 | bug-216: every fleet store's `.refmatrix_ignore` lists `CLAUDE.md` and `.claude` (cliquedb, viascope, cliquet, atldb). After bug-216 deploys, remove the `CLAUDE.md` line fleet-wide so the rule docs reach each store's graph? (The built-in include, R11, still yields to an explicit ignore line.) | (a) yes, fleet-wide after deploy; (b) refmatrix only; (c) per repo, ask each time | open |
| Q-3 | 2026-11-13 | Handhold outcome experiment: is orientation cost after `/clear` or a new session the right PRIMARY outcome, or is there a symptom of the re-derivation tax you care about more? | (a) orientation cost; (b) name another | open |
| Q-4 | 2026-11-13 | Handhold outcome experiment: may real sessions be randomised into arm B (no per-prompt injection) for a period, or opt-in only? | (a) opt-in per session; (b) randomise for a fixed period | open |
| Q-5 | 2026-11-13 | Handhold outcome experiment: which projects? | (a) refmatrix + cliquedb; (b) wider fleet | open |
| Q-6 | 2026-11-13 | "Used without being named" (a memory's rule followed, a mistake avoided): make it its own task beside 19.6's transcript scorer, designed with a sampled judge and a control? | (a) yes, draft the task row; (b) not now | open |
| Q-7 | 2026-11-13 | CONFIRM an interpreted "yes": plan-10 dedupe = (1) re-deliveries render as a one-line pointer, with the suppression tier now reopened per your follow-up, and (2) no per-prompt injection on non-human prompts (teammate, agent, bus, task notifications). `arch-10r` is writing the specs on this reading. | (a) confirmed; (b) correct it | assumed |
| Q-8 | 2026-11-13 | CONFIRM an interpreted "yes": bug-216 = resolver fix (bare doc ids bind the doc) PLUS the `denotes` link (repairs existing edges, replaces the forced re-ingest). Spec rev 3-4 and `red-216` proceed on this reading. | (a) confirmed; (b) link alone, no resolver change | assumed |

## Answered {#answered}

| id | asked | question | answer | acted |
|---|---|---|---|---|
| Q-0a | 2026-11-13 | bug-214: untrack the live store files in cliquet, atldb, prep_prolific? | "git ignore them" | untracked + ignored on the checked-out branches |
| Q-0b | 2026-11-13 | 21.5 OD-4 (19.6's scorer calls `tool_touches`) | "agree" | decision row d21-5a |
| Q-0c | 2026-11-13 | 21.5 OD-5 (W = 2) | a decaying score, plateau to lag 3 ("3 or 4") | kernel k = 3, h = 2; k = 4 sensitivity row |
| Q-0d | 2026-11-13 | AC-15 may copy cliquedb's store read-only? | "copy cliquedb" | `#ofu-cliquedb` closed |
| Q-0e | 2026-11-13 | Pilot the R12 labels before building 21.5? | "b, but not a denial of a" | `lbl-215` pilot; approval track kept |
| Q-0f | 2026-11-13 | Measure the three clique sources before deciding? | yes | `tc-215` phases 1-3 |
| Q-0g | 2026-11-13 | Add the handhold outcome exploration? | "add the exploration" | `exploration-handhold-outcome-experiment` |
| Q-0h | 2026-11-13 | Fix bug-216? | "lets fix 216" | spec + `red-216` |
| Q-0i | 2026-11-13 | Measure the already-held share of injections? | yes | `dd-10r`; 48.0% |
| Q-0j | 2026-11-13 | plan-10's "degrade, never suppress" | "can be reopened" | sent to `arch-10r` (tiered policy, pre-registered gate) |
