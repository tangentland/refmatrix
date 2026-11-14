---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-11-14 (session 37b7498f, resumed from f0521bff's 2026-11-13 handoff). No release. Deployed
is still **0.82.0**. Dev master holds spec, review-ledger, registry and decision commits only; all
code is in littlebig clones. Prior handoff archived at
`workflow/past_handoffs/020-plan10-216-251-specced_2026-11-13.md`.

rel: supersedes -> [[handoff-020-plan10-216-251-specced]]
rel: depends-on -> [[open-questions]]
rel: depends-on -> [[plan-review-2026-11-13]]

## Active goal {#active-goal}

No active goal. The user will turn the consolidated plan (`workflow/plan-review-2026-11-13.md`
`#queue` + `#goal-horizon`) into a `/goal` once the POP rewrite lands; that text is not written yet.
Delegated user gates (L77, L78): the 0.83.0 fleet deploy with `install-hooks --apply --force` over
the 8-repo roster, plan-27's memdir migration and plan-28's start run without asking, each when its
spec's preconditions hold, with the user told at the start. G18 still stops the goal.

**Agents at save time (2026-11-14, refreshed at ~84% context)** — briefs in
`workflow/agents/inflight-2026-11-14.md` (+ the L-rows below for amendments):

| agent · type | clone (`/Volumes/littlebig/…`) · branch | state | expected artifact |
|---|---|---|---|
| `green-251c` · ch-implementer | `refmatrix-plan25-1` · `task-25.1-recall-hook-byte-budget` | GREEN `dc66a04`; full suite running | full-suite log + `#green-r8` |
| `green-225` · ch-implementer | `refmatrix-bug225` · `task-bug225-handoff-trunk-from-origin-head` | src edits in tree; full suite running | GREEN commits + summary |
| `green-216` · ch-implementer | `refmatrix-bug216` · `task-bug216-rule-docs-in-graph` | RED `aac951c` + `1d2e200` + `eeaaefa` (L81/L86) | GREEN remedy + `#green-remedy-r1` |
| `green-212r2` · ch-implementer | `refmatrix-bug212` · `task-bug212-worktree-hook-crashes` | RED `1c7cf4c`..`f7578dd` (L72/L82) | GREEN r4 + `#green-r4` |

All seven spec branches are approved and frozen (merge points): T0 `fa1227d`, T2 `0fd8a2f`,
T3a `8e8e307`, T3b `5559d20`, T3c `01c1f63`, T4 `b409d98`, T56 `fa1af7d`.

## What this session did {#did}

- **Spec wave approved** (d9co route, ch-bsd rounds persisted in `workflow/bullshit/`): T0
  `fa1227d`, T2 `0fd8a2f`, T3a `8e8e307` (incl. 25.1b R18, bug-224's skip line), T3b `5023620`,
  T3c `1e89050`, T4 `b409d98`, T56 `fa1af7d` (G22 approved; its superseding memory
  `feedback_operational_content_same_partition_not_skewing` written and ADR-0003 repointed).
  Rulings L61-L83 in `workflow/plan-review-2026-11-13.md#lead`.
- **plan-28 reshaped by the user:** 3-day window (L79), orchestrator-run start (L78/L80); then Q14
  "drop the live part" (L83) after measuring real session rates (refmatrix ~0.5/day, cliquedb
  ~0.1/day) — the paired re-entry leg carries every verdict. L83 revisions in flight.
- **0.83.0 code:** 25.1 remedy GREEN (`dc66a04`); bug-212 r4 RED (32 RED, a fifth bypass
  `rmx partition drop` found); bug-216 r1 audit DIRTY 1B/2S/4M (L81 remedy RED in flight); bug-225
  (handoff trunk ignores origin/HEAD; atlftpd's trunk is develop) RED done, GREEN in flight.
- **Fleet:** roster resolved to 8 repos (no tree walk); `~/enduris/thiquet`'s LaunchAgent removed
  (plist backed up in `~/.refmatrix/backups/enduris-thiquet-daemon-2026-11-14/`); atlftpd got a
  launchd daemon; atlftpd `git remote set-head origin develop`.
- **Bugs logged:** bug-220..bug-225. New PATTERN `control-point-claim-without-census`; the
  hand-off PATTERN at 5 sightings.
- **Harness:** `CLAUDE_CODE_SHELL=/opt/local/bin/bash` (bash 5.3) in `~/.claude/settings.json`;
  takes effect after a Claude Code restart.

- **Later on 2026-11-14:** plan-28 reshaped to the paired re-entry leg only (Q14, L83, L86, L87,
  L89; approved `01c1f63`); plan-10/10.2 follow (`5559d20`). Agents get refmatrix through
  `scripts/rmx-master` + read-only MCP tools in every `ch-*` agent (Q15, L85; MCP offer verified
  only after a restart) and are read-only on live stores (`529e337`). New drafting specs, all
  queued after 0.83.0: `task-agent-start-context`, `task-linked-readonly-store` (Q16),
  `task-compaction-as-handoff` (Q17 + L91-L93: compaction and /clear write the full recall-state
  to a file, inject a pointer, and a read gate makes the agent read it). bug-226 logged.

## Open {#open}

- **Questions:** none open (next id Q18 in `workflow/open-questions.md`).
- **Recall after /clear is MANUAL until 0.83.0 deploys:** today's hooks never run `rmx recall-state` on clear or compact; run `/recall-state` yourself.
- **Next, in order:** collect the six agents → GREEN for bug-216 (L81) and bug-212 (L72+L82) →
  ch-bsd: 25.1 confirm, bug-212 r4 (range `f7c0d39..HEAD`), bug-216 r2, bug-225 → merge 25.1 →
  bug-216 (apply R4 to `.refmatrix/.refmatrix_ignore` then `rmx ingest .`; add the bug-216 →
  bug-185 order edge) → bug-212 → bug-225 → release 0.83.0, deploy → fleet `install-hooks --apply
  --force` on the 8-repo roster (full layer incl. atlftpd and bdep/thiquet, Q12) with backups and
  `.git/hooks` read back → merge the 7 spec branches (T56 before T3a; expect an ADR-0004 conflict;
  run `./scripts/lint-gmd.sh`) → G27 bookkeeping and the POP rewrite → the goal text for the user.
- **Not pushed:** dev master is ~91 commits ahead of `origin/main`; fleet commits from bug-214 too.
- **Uninvestigated:** `~/.claude` holds 231 unstaged deletions (93 under the old cliquedb memdir).

## Resume {#resume}

1. `/recall-state`; read this file, `workflow/open-questions.md` and
   `workflow/plan-review-2026-11-13.md` (`#lead` L61-L83, `#queue`).
2. `ListAgents` — any agent above still addressable is live; otherwise inspect its clone and
   re-dispatch from `workflow/agents/inflight-2026-11-14.md`.
