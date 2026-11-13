---
gmd: "0.1"
id: measurement-task-21.5-r12-pilot-2026-11-13
title: "Task 21.5 R12 labelled pilot (2026-11-13): the mechanical matcher measures proximity, not use — p_w 0.07 CAUSED / 0.19 CAUSED+INFORMED; bash_name 0/46"
tags: [measurement, plan-21, task-21.5, r12, telemetry, used, labels]
metadata:
  node_type: measurement
  status: provisional
  created: 2026-11-13
---

# Task 21.5 R12 labelled pilot, 2026-11-13 {#root}

Run by `lbl-215` at the user's direction (pilot first, approval track kept: pilot before
implementation, approval track kept). Persisted by the lead from the agent's text. Counts and
labels only; no prompt, command or memory text. **Provisional** until ch-bsd reviews it with the
term/clique measurement (`tc-215`).

rel: evidence-for -> [[task-21.5-tool-used-signal#r12]]
rel: evidence-for -> [[task-21.5-tool-used-signal#ofu-pilot]]

## Setup {#setup}

- Join: the architect's `proto5` under D15 rules, on fresh read-only APFS clones (deleted after).
  refmatrix 2026-10-20..11-13: 8,361 units, 126 headline (bands 0 / 1-3 / 4-6 / 7+ = 27/15/17/67),
  133 prior-touch. cliquedb 2026-11-04..11-11: 5,874 units, 72 headline (11/12/6/43), 143
  prior-touch (exact match to spec rev 3.1).
- Sample: seed 21513, `random.Random(f"21513-{corpus}")` over pairs sorted by (session, prompt,
  channel, key, touch ts); up to 20 per band, 20 prior-touch, 20 control (R7 per-call rule) per
  corpus. 201 pairs labelled; UNJUDGEABLE 0. Five labeller forks, one rubric.
- Labels: CAUSED / INFORMED / CONSISTENT / UNRELATED, judged from the session transcripts.

## Label counts {#counts}

C / I / CONSISTENT / UNRELATED, all origins `[main loop]`.

| corpus | stratum | all | main loop |
|---|---|---|---|
| refmatrix | lag 0 | 1/2/14/3 (20) | 1/2/10/2 (15) |
| refmatrix | lag 1-3 | 1/1/10/3 (15) | 0/1/6/0 (7) |
| refmatrix | lag 4-6 | 0/1/12/4 (17) | 0/1/3/2 (6) |
| refmatrix | lag 7+ | 0/0/15/5 (20) | 0/0/9/3 (12) |
| refmatrix | prior-touch | 0/1/17/2 | 0/0/3/0 |
| refmatrix | control | 0/0/12/8 | 0/0/5/2 |
| cliquedb | lag 0 | 2/0/6/3 (11) | 1/0/4/0 (5) |
| cliquedb | lag 1-3 | 0/1/1/10 (12) | — (0) |
| cliquedb | lag 4-6 | 1/1/1/3 (6) | 1/1/1/0 (3) |
| cliquedb | lag 7+ | 0/1/8/11 (20) | 0/1/0/0 (1) |
| cliquedb | prior-touch | 0/0/10/10 | 0/0/2/1 |
| cliquedb | control | 0/0/10/10 | — (all 20 subagent) |

## Precision {#precision}

CAUSED / judged; (CAUSED + INFORMED) / judged; Wilson 95%.

- refmatrix, 72 headline: 0.03 [0.01, 0.10]; 0.08 [0.04, 0.17]. Main loop (40): 0.03 [0.00, 0.13]; 0.12 [0.05, 0.26].
- cliquedb, 49 headline: 0.06 [0.02, 0.17]; 0.12 [0.06, 0.24]. Main loop (9): 0.22 [0.06, 0.55]; 0.44 [0.19, 0.73].
- Pooled main loop by band: lag 0 2/20 = 0.10 [0.03, 0.30], C+I 4/20 = 0.20 [0.08, 0.42]; lag 1-3 0/7, 1/7; lag 4-6 1/9, 3/9; lag 7+ 0/13 [0, 0.23], 1/13 [0.01, 0.33]. Every band < 20 main-loop pairs.
- Prior-touch pooled: 0/40 [0, 0.09]; 1/40.
- Kernel-weighted `p_w` (k = 3, h = 2, inverse sampling fraction, Kish n_eff): pooled main loop C 0.073 [0.023, 0.213], C+I 0.194 [0.094, 0.357], n_eff 33.1; pooled all origins C 0.059, C+I 0.128, n_eff 77.4. {#p-w}

R12 gates: n_main 49 pooled (< 50, report-only); subagent share 60% (ceiling 10%); `p_w` < 0.50 on both definitions — the "matcher or kernel is revised" row. {#gates}

## Breakdowns {#breakdowns}

- **match_on:** `bash_name` 0 CAUSED of 46, C+I 1/46 = 0.02 [0.00, 0.11] (main loop 0/23 [0, 0.14] — meets R12's per-stratum drop rule); `bash_path` C 5/75, C+I 11/75 = 0.15 [0.08, 0.24], main loop C+I 9/26 = 0.35 [0.19, 0.54] — all of the signal; `path` / `name` / `mcp_name` were absent from the sample (none of the 121 sampled headline pairs used them).
- **item kind:** term concepts 0/40 C+I; grep-floor names 0/24; doc anchors C 3/43, C+I 8/43; code 1/7; memory C+I 3/5.
- **channel:** scan_prompt C+I 8/113 = 0.07; prompt_recall 2/4; context 1/3; session_start 1/1.
- **origin:** main loop C+I 9/49 = 0.18; subagent 3/72 = 0.04 (scan_prompt deliveries never reach a subagent). {#by-leg}

## The control {#control}

0 of 40 control pairs had any route from the item (22 CONSISTENT, 18 UNRELATED; 17 of the 18
UNRELATED are `bash_name` hits on generic tokens). The control is name-leg-heavy (28/40 vs 46/121
in the headline); cliquedb's control is all subagent. Headline non-use is 109/121 — the control's
shape — so lift near zero is explained: the control is not biased low; the headline carries the
same noise floor.

## Verdict (provisional) {#verdict}

As specified, the instrument measures proximity, not use: about 90% of headline credits are
touches the agent would have made anyway, or coincidences. Real use appears only in the main-loop
`bash_path` leg on doc-anchor, memory and code items, mostly at lag 0 and 4-6. The lag 7+ tail is
0 CAUSED of 40.

## Matcher changes the labels point to {#matcher-changes}

1. Drop or gate `bash_name` (0/46 CAUSED; generic tokens, and 8 of 14 refmatrix lag 0-3 pairs were the user's own prompt words echoed by scan_prompt's delivery).
2. Exclude subagent touches until origin is live (19.0 R2 / 24.6 R4).
3. Order by the call's start, not the ring ts (3 self-deliveries credited at lag 0).
4. Do not tokenise heredoc or commit-message bodies; a path in a shell variable is unknown (reopened D15's clone leg in several pairs).
5. Resolve a worktree-isolated subagent's relative paths against its worktree (8 cliquedb pairs).
6. Exclude term-concept and grep-floor items from the tool leg (0/64 C+I).
7. Attribution artefacts: R5 gives a re-delivered file's credit to the later unit; a subagent's own context delivery and the main loop's scan unit both credit one touch.

## Caveat {#caveat}

The rubric left one call open: a subagent opening a file for its own brief with no route from the
delivery was CONSISTENT in four chunks and UNRELATED in one. It moves only the
CONSISTENT/UNRELATED split, never CAUSED or INFORMED. Working files (pair ids, labels, one-line
paraphrases) stay in the session scratchpad and are not committed.

## Review corrections (ch-bsd m1, 2026-11-13) {#review-m1}

rel: amends -> [[bsd-215m1-measurements-r1]]

Pilot counts and `p_w` reproduced exactly ([[bsd-215m1-measurements-r1#verdict-lines]]). "Measures
proximity, not use" holds for "caused the touch"; it is weaker as a claim about usefulness, since
the rubric cannot see a detour a delivery prevented. The CONSISTENT ↔ UNRELATED split is wider
than [[#caveat]] says: 5 of 26 blind pairs (19%), all subagent touches; no CAUSED/INFORMED label
is affected ([[bsd-215m1-measurements-r1#s5]]). Blind agreement on CAUSED+INFORMED vs not: 25/26,
with no original positive in the blind set.
