---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-11-11 (session 7efc36ce, resumed from 7aea273d's 2026-11-10 handoff). Released and
deployed 0.82.0. Prior handoff archived at
`workflow/past_handoffs/018-wave0-plan24-specs-hypertree_2026-10-20.md`.

rel: supersedes -> [[handoff-018-wave0-plan24-specs-hypertree]]
rel: depends-on -> [[plan-of-plans#goal-2026-11-10-progress]]

## State {#state}

- **Deployed: 0.82.0** (release `9432b83`; hub + 8 daemons verified 0.82.0 from `~/refmatrix`,
  no `[DEV TREE]`, hub under launchd; no `FatalException` since the restarts). Deploy tree at
  `afda6ff` (src unchanged since the release). `origin/main` = `afda6ff` (pushed).
- **Shipped in 0.82.0:** plan-26 26.2 (`05164ce`, ch-bsd r3 GO) + 26.3 (`fdc6359`, r2 GO) + AC-4c
  (`078c951`); bug-199/200 (`6c2abb2`, `54e4f70`); user-level `/save-state` + `/recall-state`
  (`3842f6d`); the loud-sync-failure requirement (user, 2026-11-10: "if the sync stops in an
  error, it needs to fail loudly on the commandline or console, not just logs").
- **Release suite** (`037d10c`): 4265 passed, 14 failed — 13 by E line = bug-127/168, bug-168 x9,
  bug-170, bug-196 x2; 1 = the GMD lint gate, fixed as bug-211 (`577287d`).
- **Fleet hooks re-installed** (user decision: full install in all 5 + refmatrix): refmatrix,
  cliquedb, orderly, atldb, viascope, cliquet all `--check` in sync, 0 foreign hooks lost,
  4/4 loud git hooks each. Backups: `~/.refmatrix/backups/hooks-0.82.0/`. cliquedb and viascope
  now run the full rmx Claude hook layer for the first time.
- **Live cut-hook repair re-run** (bug-199): 11 derived dropped, 9 curated restored from
  `hooks29-draft.json`; after a write: 0 `…` values, 9/9 restores intact, "nothing to repair".

rel: depends-on -> [[impl-task-user-level-state-commands#deploy-cleanup]]

## Open items {#open}

- **User to run:** the fleet command cleanup for the 7 repos that TRACK `/save-state` +
  `/recall-state` — script `/private/tmp/claude-501/-Users-tholley-claude-tools-refmatrix/7efc36ce-3694-46b6-b30c-31160ae25396/scratchpad/fleet-command-cleanup.sh`
  (trunk commits in throwaway worktrees for cat-herder, cliquedb, cliquet, prep_prolific,
  thiquet; on the current branch for atldb, portal). The 6 untracked copies (atlftpd, orderly,
  viascope) are deleted; all 40 copies backed up in `~/.refmatrix/backups/commands/fleet-0.82.0/`.
- **User to commit** in the fleet repos: the hook install's `.claude/settings.json`,
  `.claude/rmx-hooks.json`, `.refmatrix/CLAUDE.md` (and viascope's `settings.local.json`).
- **Recount** `…` values in the refmatrix memdir sidecar after the next save-state (bug-199).
- **`/mcp` reconnect** in every open client to load 0.82.0's MCP server.
- **Store derive:** `rmx daemon status` here says gmd/pagerank are behind code
  (`rmx reingest --force`) and memory-compile has no stamp — pre-existing, not run.
- **Open rows:** bug-201 (rich eats `[daemon]`), 203 (`sync -i` purges on the replica), 206
  (in-place dropped heading's anchor lingers), 207 (in-process sync never closes its Store), 208
  (non-atomic save-state write — before 26.5), 209 (`--check` blind to `.git/hooks`), 210 (26.2
  r3 MEH follow-ups, m3-1 first), 177 (Stop promote timeout behind a long sync, seen 2);
  pre-existing suite rows bug-127/168, 170, 190, 194, 196. 2 live memories lost all anchors
  before 0.82.0 (bug-202 note) — restore needs 26.5's forced re-bridge.
- **Plan-26 order:** 26.4 → 26.5 (rollback-moves-`savestates/`-back AC, `b5ed7b3`) → 26.7 →
  26.6 R3 residual → 26.8; then bug-185 → 23.2 → 23.1 → 23.3 ∥ 23.5; plan-25 and plan-27
  (now carries the fleet-hook exception, `9780579`) after their dependencies.
- **littlebig:** the plan26-2, plan26-3 and bug199-200 clones are merged and can be retired at
  the user's word; four October store-copy scratch dirs kept by the user's choice.

## Resume {#resume}

1. `/recall-state`; read this file and `workflow/plan-of-plans.md`.
2. Confirm the user ran the fleet command cleanup; re-scan with the inventory in
   [[impl-task-user-level-state-commands#deploy-cleanup]] step 1.
3. Next work: bug-210 m3-1 (bound the whole-batch re-queue), then the plan-26 order above.
