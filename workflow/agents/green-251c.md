---
gmd: "0.1"
id: agent-brief-green-251c
title: "Brief: green-251c — task 25.1 rev-7 GREEN (ch-implementer)"
tags: [agent-brief, dispatch]
---

# Brief: green-251c — task 25.1 rev-7 GREEN (ch-implementer) {#root}

Dispatched 2026-11-13 (session f0521bff) as `ch-implementer`. Make 25.1's rev-7 REDs pass; write no
tests. Rev 8 (hard 9,500 B cap + degrade ladder + spill page, Q14) is NOT in this round.

- **Clone:** `/Volumes/littlebig/refmatrix-plan25-1`, branch `task-25.1-recall-hook-byte-budget`
  (GREEN `16ace00`; red-rev7 `1f9459a`, `61587f0`; spec rev 7 + follow-up `c1fae32`; rev 8 spec
  `cec8afe`, `4f95c23`).
- **Read:** spec `#rev-round-7`, `#rev-round-7-followup`; summary `#green`, `#red-rev7`,
  `#red-rev7-ambiguities`; `workflow/agents/green-251.md` (hard rules, merge hygiene).
- **REDs:** J3/J4 subjects exempt from cross-encoder rerank, keeping their pre-rerank index (a-j4);
  J5 SessionStart `--k 12` + regenerate `.claude/settings.json`, `rmx-hooks.json`, README hooks
  table with the clone's interpreter; F6 the `recall leg` line only under `--verbose`; F2
  recall-state counted as producer `recall_state` (a-f2); F1 `bus_pub` gains `about`, `project` is
  the transport target only, CLI `--about`. AC-5 stays RED until 26.4 merges.
- **Amendment (lead, after dispatch):** do not add any hook-output path that bypasses a single emit
  point; report where every generated hook command writes its stdout today (for rev 8).
- **Verify:** 13 touched files (only AC-5 fails); family; full suite by E line; mutations J3/J4,
  F6. Tee to `workflow/review-output/plan25/`. Commits: src + regenerated files, `#green-rev7`.
