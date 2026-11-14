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

**Agents at save time (2026-11-14)** — all six were stopped by the weekly usage limit and told to
resume after it reset; briefs in `workflow/agents/inflight-2026-11-14.md`:

| agent · type | clone (`/Volumes/littlebig/…`) · branch | base | expected artifact |
|---|---|---|---|
| `green-225` · ch-implementer | `refmatrix-bug225` · `task-bug225-handoff-trunk-from-origin-head` | RED `be9acae` (+ uncommitted src) | GREEN commits + summary |
| `red-216` · ch-test-engineer | `refmatrix-bug216` · `task-bug216-rule-docs-in-graph` | `df092ac` (+ uncommitted test file) | L81 RED commits |
| `green-251c` · ch-implementer | `refmatrix-plan25-1` · `task-25.1-recall-hook-byte-budget` | GREEN `dc66a04` | full-suite log + `#green-r8` |
| `red-212r2` · ch-test-engineer | `refmatrix-bug212` · `task-bug212-worktree-hook-crashes` | `3224a14` (+ uncommitted test edits) | L82 RED commits |
| `spec-t3c` · ch-architect | `refmatrix-spec-t3c` · `spec-wave-t3c` | `1e89050` | L83 revision (paired leg only) |
| `spec-t3b` · ch-architect | `refmatrix-spec-t3b` · `spec-wave-t3b` | `5023620` | L83 revision (10.2 without live draw) |

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

## Open {#open}

- **Questions:** none open (next id Q15 in `workflow/open-questions.md`).
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
