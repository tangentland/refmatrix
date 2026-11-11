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

## Active goal {#active-goal}

No active goal (no `/goal` was set this session).

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

## In flight at save (2026-11-11) {#in-flight}

Four agents were running in littlebig clones (each cloned from dev `master` `f7c0d39`; `.venv-eval`
is a symlink to the dev tree's). Their next artifact is a commit on the clone's branch; ch-bsd
reports may come back as text for the lead to persist ([[reference_subagent_reports_returned_as_text]]).

| agent · type | clone (`/Volumes/littlebig/…`) · branch | state at save | next |
|---|---|---|---|
| `green-bug212` · ch-implementer (DONE) | `refmatrix-bug212` · `task-bug212-worktree-hook-crashes` | GREEN src `b6357ca` + summary/logs `b024a95`: RED file 19/19, family 110, wide 592; mutations g/z/c/w killed. One store definition `store.WRITER_CATALOG_FILES` (hooks render the gate from it); post-checkout skips a null old sha; `sync.GitRefError` → clean `Error:` (in-process + daemon); `cli._cwd()` → clean error, `rmx version` still works. Flags: a project whose `.refmatrix/` has only `partition` (store via `REFMATRIX_ROOT`) no longer syncs from git hooks; `docs/INTEGRATION.md#git-integration` not updated; one manual probe appended a row to the live `~/.refmatrix/cli.log`; clones' symlinked `.venv-eval` makes the SkipGate call `test_repo_hooks_in_sync`'s skip UNPINNED (log a row) | NOT YET DISPATCHED: ch-bsd r1 over `f7c0d39..b024a95`; update INTEGRATION.md; then merge |
| `green-264` · ch-implementer | `refmatrix-plan26-4` · `task-26.4-savestate-mtype-normalisation` | RED `bbd706d`+`c55afc8` (17 RED), deferral row `bf33236`; GREEN mid-run (uncommitted src) | lead decision: ADR-0005 wins (top-level `savestate_*` + `savestates/` only); mutations o/s/t/u/f; ch-bsd; merge BEFORE 25.1 |
| `red-251` · ch-test-engineer | `refmatrix-plan25-1` · `task-25.1-recall-hook-byte-budget` | R0 measured `d748196` (outcome A, per hook, 10,000 UTF-16 units → 9,000 B per command); RED mid-run | then GREEN, ch-bsd, merge after 26.4 |
| `bsd-215` · ch-bsd (DONE) | `refmatrix-plan21-5` · `task-21.5-tool-used-signal` | spec r1 DIRTY 18 (3B/7S/8M) + addendum vs 24.6 r5 (3S/1M); NOT approval-ready; report persisted by the lead `d8ae624` (`workflow/bullshit/2026-11-11-1312-task-21.5-spec-r1-15e8f64.md`). B: `v: 2` is malformed to `row_provenance` (+2 tests pin it); memories have no `Entity.path` (use `metadata.source_path`); Agent/mcp legs unreachable (hook matcher is 8 tools) | architect revision r1, deciding as the user would: keep Agent/mcp legs "live from 24.6 R4" + 24.6 AC-3 adds an Agent and an mcp call; credit per (tool call, file); R1 records `tool_use_id` + one origin field (`origin` per 19.0 R2), the labeller records origin from the transcript; headline excludes prior-touch (both printed); OD-4 signature `(tool_name, tool_input, cwd)` + ring adapter; OD-5 after s-1/s-6; 24.6 r6 for x-1..x-3. Then spec r2. Ledger lines still to land on master: INDEX/last_run (in the report) + 2 IMPRESSIONS bullets AFTER folding the oldest (IMPRESSIONS has 49 run bullets) |

If an agent is gone on resume: read its clone's newest commit body and `git status`, then start a
fresh agent of the same type with the task's spec, the bug row or summary stub, and "resume from
<branch>@<tip>; inspect any uncommitted work first". Release plan: one 0.83.0 for bug-212 + 26.4 +
25.1 (+ 21.5 if ready), then one fleet `install-hooks --apply --force` (bug-212 and 25.1 change the
generated hooks), verifying `.git/hooks` by reading them (bug-209).

rel: related-to -> [[project_0820_release_fleet_hooks]]

## Open items {#open}

- **Release items closed (2026-11-11):** fleet command cleanup committed in the 7 tracking repos
  (trunks: cat-herder `09a4997`, cliquedb `e946d0d`, cliquet `d5a4bc7`, prep_prolific `1d48803`,
  thiquet `c74f571`; current branch: atldb `fc8ee67`, portal `4b104b1c`); hook-install files
  committed by pathspec (cliquedb `b4a66e2`, atldb `83fcc1e`, viascope `5244c8720`, cliquet
  `41aa6db`); `/mcp` reconnected here; bug-199 re-counted after a save-state (0 `…`, 9/9 held).
- **Not pushed** in any fleet repo — the user pushes. cliquedb's `origin/main` still carries the
  pair until `e946d0d` is pushed; the feature branches (gmd-conformance-sweep x3, nr-native-recast,
  cliquedb's 10 agent worktrees) drop it when they merge their trunk.
- **Left uncommitted on purpose:** orderly's hook files (the repo has no commits yet) and
  viascope's `.claude/settings.local.json` (it carried someone else's uncommitted edits).
- **Other open clients** still need `/mcp` reconnect for 0.82.0's MCP server.
- **Store derive (done 2026-11-11):** no force reingest — only pagerank's code had moved
  (ingest/semantic/embed are version-label drift; gmd re-derived at 0.82.0). `rmx pagerank`:
  85,400 -> 101,784 scored nodes (graph grew 86.9k -> 112.4k entities since 0.77.1).
  `rmx memory compile --apply`: 57 subjects (0 unlabeled, 262 of 278 memories), 30 July-era
  subjects marked stale (15 `unlabeled-N` + junk labels; rows kept), declared subject untouched.
  A few new labels are weak (`github-0e9e309f`, `github-bca1c694`, `allowed`, `cwd`, `store`) —
  rename via `focus change-subject` if wanted.
- **Open rows:** bug-201 (rich eats `[daemon]`), 203 (`sync -i` purges on the replica), 206
  (in-place dropped heading's anchor lingers), 207 (in-process sync never closes its Store), 208
  (non-atomic save-state write — before 26.5), 209 (`--check` blind to `.git/hooks`), 210 (26.2
  r3 MEH follow-ups, m3-1 first), 177 (Stop promote timeout behind a long sync, seen 2);
  pre-existing suite rows bug-127/168, 170, 190, 194, 196. 2 live memories lost all anchors
  before 0.82.0 (bug-202 note) — restore needs 26.5's forced re-bridge.
- **Plan-26 order:** 26.4 → 26.5 (rollback-moves-`savestates/`-back AC, `b5ed7b3`) → 26.7 →
  26.6 R3 residual → 26.8; then bug-185 → 23.2 → 23.1 → 23.3 ∥ 23.5; plan-25 and plan-27
  (now carries the fleet-hook exception, `9780579`) after their dependencies.
- **littlebig (2026-11-11):** merged clones plan26-2, plan26-3, bug199-200, plan26-6 removed
  (each verified: no uncommitted work, no stashes, every branch in dev `master`). Active:
  `refmatrix-bug212`, `refmatrix-plan26-4`, `refmatrix-plan25-1`, `refmatrix-plan21-5`. Kept by
  the user's earlier choice: the October scratch dirs (`refmatrix-bug105-probe`,
  `refmatrix-spike-hypertree`, and the store copies).
- **plan-24 24.6 amended (r5, `99d96c7`):** the mod's tool observe writes 21.5's ring fields and
  emits no `used` (user decision on 21.5 OD-1).

## Resume {#resume}

1. `/recall-state`; read this file and `workflow/plan-of-plans.md`.
2. Confirm the user ran the fleet command cleanup; re-scan with the inventory in
   [[impl-task-user-level-state-commands#deploy-cleanup]] step 1.
3. Next work: bug-210 m3-1 (bound the whole-batch re-queue), then the plan-26 order above.
