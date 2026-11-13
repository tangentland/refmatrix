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

## Session 37b7498f (2026-11-13) {#session-37b7498f}

Next id: **Q9**.

### Open {#open-37b7498f}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|

### Answered {#answered-37b7498f}

| id | asked | question | answer | acted |
|---|---|---|---|---|
| Q8 | 2026-11-13 (restated three times; bsd-pop-r3 R1, r4 W1, r5 Y1) | Q1 follow-up, a GOAL PRECONDITION (W2: option b changes what items 1-3 build): what does "save-states and `workflow/` OUT of the graph" mean? Facts: save-states reach the store only through the memory bridge, as `session/recall-state` rows that `rmx memory recall` can return; STM digests (`session/digest`) are written by `memory_add`, not the bridge, and are treated like save-states below; `.refmatrix_ignore` is project-root relative and does not govern the bridge; an ignore line for `workflow/` purges its entities through sync, which is audited only after 22.6 R3. Your rule's two reasons: workflow content dominates co-mention weights, AND it goes stale and contradicts current code (temporal, not structural). What "viascope's rule" says: its `.refmatrix_ignore` header lists save-states with plans, handoffs and bsd reports as content kept OUT of the concept graph (its mechanism reached them because they then lived under `workflow/`), AND says that excluded content "stays reachable via `rmx session recall` and `rmx memory recall`". So for `workflow/` every option but c is literal; for save-states, b follows the rule's mechanism (out of the store) and a follows its stated intent (out of the graph, still in memory recall) | a (user, 2026-11-13: "q8-q" then "q8-a"; read as a typo correction) | D-Q1 confirmed as option a: `workflow/` OUT at ingest (removed through plan-22's audited path after 22.6 R3; rel: edges into it lose targets); save-states + digests stay in the store and memory recall, excluded from co-mention by a derive-time filter; G22 un-held and specced in T6 |
| Q1 | 2026-11-13 | Which content may enter a project's concept graph? (X2 in [[plan-review-2026-11-13#x2]]: memories-in vs `feedback_operational_content_not_in_graph`) | a (CONFIRMED by Q8 = a) — memories IN, correctly classified; save-states and `workflow/` OUT (viascope's rule, fleet-wide) (user, 2026-11-13: "q1-a, q2-ship it, q-3-7 your recommendations") | lead's reading (stated to the user): OUT = excluded from co-mention / concept-weight derivation, not from ingest; `workflow/` docs stay addressable by name, anchor and `rel:` (corpus root per PROJECT_PROFILE); task stub to T6 |
| Q2 | 2026-11-13 | 25.1 rev 7 is built ahead of its recorded dependency on 26.7 and plan-27 (X3, [[plan-review-2026-11-13#x3]]); rev 8 is specced on the same branch, unbuilt. Ship rev 7 in 0.83.0? | "ship it" = b: rev 7 ships in 0.83.0; waiver recorded; 26.7 AC that 25.1's curated-hook lookup survives the regroup; rev 8 becomes task 25.1b on its own branch after 10.3 (user, 2026-11-13: "q1-a, q2-ship it, q-3-7 your recommendations") | green-251c told; rev-8 spec text moves off the 25.1 branch into task 25.1b before the merge |
| Q3 | 2026-11-13 | P3 freezes context-delivery building, which narrows your d9bi (plan-19 leads Wave 1 as helix's substrate). Freeze what? (X4, [[plan-review-2026-11-13#x4]]) | a (lead's recommendation) (user, 2026-11-13: "q1-a, q2-ship it, q-3-7 your recommendations") | P3 narrowed: freeze 19.2, 19.6 phasing/cache + Table C, 21.3, 21.5 build only; d9bi narrowed, not reversed |
| Q4 | 2026-11-13 | Your recorded order is 21.5 decision → handhold experiment; the pilot fired 21.5's lowest band (p_w 0.07 < 0.50), so rev 3.1 as written builds a matcher the labels reject (X5, [[plan-review-2026-11-13#x5]]). Which gates which? | a (lead's recommendation) (user, 2026-11-13: "q1-a, q2-ship it, q-3-7 your recommendations") | 21.5 rev 4 folds the pilot's seven matcher changes; 21.5 decision = no build until the handhold experiment reports; experiment runs after |
| Q5 | 2026-11-13 | plan-24 D1 says hook-shaped work (plan-16, 19.5 R1, 19.6 injection, 21.2-21.4) is NOT built on hooks but retargets to the mod; nothing queued builds 24.5/24.6, and 25.1 already builds 19.5 R1 on hooks (X6, [[plan-review-2026-11-13#x6]]). | a (lead's recommendation) (user, 2026-11-13: "q1-a, q2-ship it, q-3-7 your recommendations") | plan-24 D1 superseded: verb-side logic builds on the hook transport now; plan-24 re-planned after the charter decision; amends note on #phasing, 24.8 R5 rows |
| Q6 | 2026-11-13 | Close the legacy in-progress plans? (X7, [[plan-review-2026-11-13#x7]]) | a (lead's recommendation) (user, 2026-11-13: "q1-a, q2-ship it, q-3-7 your recommendations") | plans 3 + 9 close now; 6/7/8/15 keep gates (W2-a, W2-c, W2-b, W1-e scheduled); plan-2 closes when #s-2/#m-4 move into 25.1b; plan-7 deferrals + G11 re-owned |
| Q7 | 2026-11-13 | 25.4/25.5 build BRE translation into grep legs that 16.5 (your 2026-10-07 decision) deletes; their premise (every agent grep reaches `rmx grep`) is false while learn.off is set (X8, [[plan-review-2026-11-13#x8]]). | a (lead's recommendation) (user, 2026-11-13: "q1-a, q2-ship it, q-3-7 your recommendations") | 16.5 wins on named-path + stdin legs; 25.4/25.5 shrink to the path-less index leg (translate vs floor decided there); bug-167 interim only if 0.83.0 needs it |

## Session f0521bff (2026-11-13) {#session-f0521bff}

Next id: **Q15**.

### Open {#open}

| id | asked | question | options (lead's recommendation first) | status |
|---|---|---|---|---|

### Answered {#answered}

| id | asked | question | answer | acted |
|---|---|---|---|---|
| Q14 | 2026-11-13 | How should hook output live within the 9.5k hard limit? | a: degrade ladder + spill to pull; clamp as counted safety net | 25.1 rev 8: R12-R14, AC-16..AC-18; RED/GREEN after the rev-7 GREEN |
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
