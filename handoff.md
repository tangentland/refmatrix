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
  `638c5cc` (src unchanged since the release). `origin/main` = dev `master` (pushed through `eb38f6e`).
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

Agents running in littlebig clones (each cloned from dev `master` `f7c0d39`; `.venv-eval`
is a symlink to the dev tree's). Their next artifact is a commit on the clone's branch; ch-bsd
reports may come back as text for the lead to persist ([[reference_subagent_reports_returned_as_text]]).

| agent · type | clone (`/Volumes/littlebig/…`) · branch | state at save | next |
|---|---|---|---|
| `bsd-212r1` · ch-bsd (DONE) | `refmatrix-bug212` · `task-bug212-worktree-hook-crashes` | r1 over `f7c0d39..b024a95`: **DIRTY 8 (1B/3S/4M), merge NO-GO until b-1**; report persisted by the lead `7537965` (`workflow/bullshit/2026-11-11-1342-bug212-r1-b024a95.md`); ledger on master. B: the file-presence store gate passes in repos that TRACK their catalogs (cliquet, atldb, prep_prolific → bug-214, user decision) — a worktree commit writes the tracked catalog. S: vanished cwd + `REFMATRIX_ROOT` still a traceback (`discovery.partition_marker`; one shared cwd helper); no fleet verifier — the 0.82.0 re-install MISSED atlftpd + bdep/thiquet (still pre-26.2 silent bodies; bug-209 now recurring, land it in 0.83.0); INTEGRATION.md git section stale. M: cwd-less telemetry row unpinned; `GitRefError(RuntimeError)` base unpinned; root commit is a loud failure (diff vs empty tree); clone SkipGate exit 1 (bug-215) | PAUSED (user, 2026-11-11): remedy r1 (gate on the daemon socket or an untracked catalog + RED for tracked-catalog worktree/clone; shared cwd helper; INTEGRATION.md; m-1..m-3), then r2 |
| `red-264` · ch-test-engineer (DONE) | `refmatrix-plan26-4` · `task-26.4-savestate-mtype-normalisation` | GREEN `1a1f189` + docs `3831499` + row wording `9460695`; f1 KILLED by `f371024` (misfiled `feedback/savestate_*` stays `project`, 4 legs; + AST pin: every as-memory `ingest_gmd_paths` call passes `marker_roots`, 3 sites) + logs `1caf3df`; file 23/23. green-264's flag is real on a different path: CLI `ingest-gmd` on a FILE/SUBDIR target misjudges the predicate both ways → **bug-213**, deferred to 26.5 (lead decision) | PAUSED (user, 2026-11-11): next is ch-bsd over `f7c0d39..1caf3df`; merge BEFORE 25.1 |
| `green-251` · ch-implementer (**RUNNING at save**) | `refmatrix-plan25-1` · `task-25.1-recall-hook-byte-budget` · base `45d8abf` | RED done by `red-251` (`36bfaa7`..`45d8abf`, 116 fail / 10 pass at HEAD). GREEN is UNCOMMITTED in the clone at save (src: cli, handoff, hooks, mcp, recall, scan, verbs + new `hook_budget.py`, `recall_pack.py`; regenerated `.claude/settings.json`); interim 119 pass / 7 fail on the RED files — AC-5 (expected until 26.4 merges) + six it calls test calibration (ac9 multiline trailer, ac4f doc-in-top-8, ac6 include-subjects ×2, ac9 session-start bodies, ac10 delivered events), which the lead has NOT accepted: #3/#4 (daemon default rerank buries all 5 subjects at ranks 32-36) and #2 (no doc reaches top 8) are to be measured as possible PRODUCT findings. It made prompt_recall pointer-only by rule (d3). At save it was waiting on a background full-suite run, then: GREEN commit, AC-14/AC-4 (i)/AC-15 (m32-m37) mutations, `workflow/measurements/plan-25-hook-bytes.md`, the a12 bare recall-state probe. Brief + 2 amendments: `workflow/agents/green-251.md` | if gone on resume: inspect the clone's uncommitted src FIRST (it is the GREEN), then a fresh ch-implementer from the brief, "resume from 45d8abf; the clone holds uncommitted GREEN". Then (after the user's go) judge the six with red-251, ch-bsd, merge AFTER 26.4 |
| `arch-215r1` · ch-architect (DONE) | `refmatrix-plan21-5` · `task-21.5-tool-used-signal` | master merged `29e3b15` (24.6 r5); **spec 21.5 rev 2 `d66543c`** closes all 18 r1 findings + x-1..x-4 (table at the spec's `#rev-2`); **24.6 r6 `540ab50`** (tool observe for every tool; AC-3 adds Agent, `mcp__refmatrix__` and subagent calls; AC-12 prompt_id shared). Key calls: b-1 no schema bump (`path` joins RECALL_EVENT_FIELDS_V1, v stays 1; row_provenance + 21.1 tests unchanged); memory path via `metadata.source_path` (`telemetry.item_path`); Agent/mcp legs "not-yet-producing" until 24.6. Join re-prototyped on APFS clones (counts only): 62 credited units (44 prior-touch, 18 headline); all 2,366 prompt-time deliveries anchor by query_id; 269/348 Read/Edit/Write touch `/Volumes/littlebig` (counted `refs_outside_project`). No src. **User decisions open** (spec `#open-for-user`): OD-4 approve the d9v row (19.6's scorer calls `tool_touches`; evidence named `tool`) — architect recommends approve; OD-5 confirm W = 2 prompts (ambient included) + R12's numbers before AC-15 output is read — architect recommends confirm | PAUSED (user, 2026-11-11): ch-bsd spec r2 over `d8ae624..540ab50` |

If an agent is gone on resume: read its clone's newest commit body and `git status`, then start a
fresh agent of the same type with the task's spec, the bug row or summary stub, and "resume from
<branch>@<tip>; inspect any uncommitted work first". Release plan: one 0.83.0 for bug-212 + 26.4 +
25.1 (+ 21.5 if ready), then one fleet `install-hooks --apply --force` (bug-212 and 25.1 change the
generated hooks), verifying `.git/hooks` by reading them (bug-209).

rel: related-to -> [[project_0820_release_fleet_hooks]]

## Open items {#open}

- **PAUSED by the user (2026-11-11): "when the current agents are finished pause and save state".**
  No new agents until the user says go. Held next steps: 26.4 ch-bsd (`f7c0d39..1caf3df`) → merge;
  bug-212 remedy r1 (b-1 gate on socket / untracked catalog, s-1 shared cwd helper, s-3
  INTEGRATION.md, m-1..m-3) → r2; 21.5 ch-bsd spec r2 (`d8ae624..540ab50`); 25.1 judge the six
  interim failures, ch-bsd, merge after 26.4. Release 0.83.0 must also land bug-209 (`--check` sees
  `.git/hooks`) and re-install the fleet found by hook MARKER (atlftpd + bdep/thiquet were missed
  in 0.82.0).
- **User decisions open:** (1) bug-214 — untrack the live `.refmatrix/` store files in cliquet,
  atldb, prep_prolific (`git rm --cached` + `.gitignore`)? bug-212 can be made safe either way.
  (2) 21.5 OD-4 — approve the d9v row (19.6's scorer calls `tool_touches`, evidence `tool`);
  architect recommends approve. (3) 21.5 OD-5 — confirm W = 2 prompts (ambient included) + R12's
  numbers before AC-15's output is read; architect recommends confirm.
- **New rows this session:** bug-213 (ingest-gmd on a file/subdir target misjudges the save-state
  predicate; → 26.5), bug-214 (fleet repos track store files), bug-215 (clone SkipGate exit 1);
  bug-209 recurring.

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
