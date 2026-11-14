---
gmd: "0.1"
id: handoff
title: "Session Handoff for refmatrix"
tags: [handoff, session]
metadata:
  node_type: handoff
---

# Session Handoff for refmatrix {#root}

Date: 2026-11-14 (session a9b75923). Every 0.83.0 candidate is merged on dev master and the
release commit is `af83867` (version 0.83.0). Deployed is still **0.82.0** (daemon pid 54024).
The user said "go ahead with the deploy when the suite passes"; the full suite on `af83867` was
running at save time (`workflow/review-output/release-0.83.0-full.log`). Prior handoff archived at
`workflow/past_handoffs/021-0830-candidates-in-review_2026-11-14.md`.

rel: supersedes -> [[handoff-021-0830-candidates-in-review]]
rel: depends-on -> [[open-questions]]
rel: depends-on -> [[plan-review-2026-11-13]]

## Active goal {#active-goal}

No active goal. Delegated user gates (L77, L78) still stand: the 0.83.0 fleet deploy with
`install-hooks --apply --force` over the 8-repo roster runs without asking (and the user has
explicitly authorised the deploy behind the suite), plan-27's memdir migration and plan-28's
start each run when their spec's preconditions hold, with the user told at the start.

**Agents at save time:** none in flight. Every agent of this session is idle with its work
committed on its branch and merged. `workflow/agents/inflight-2026-11-14.md` is historical.

## What this session did {#did}

- **Merged to master** (each through RED → GREEN → ch-bsd until GO; rulings in
  `workflow/plan-review-2026-11-13.md#lead`):
  - 25.1 recall-hook byte budget `d44e359`, then its r9 MEHs `d1be40a` (bsd r10 CLEAN).
  - bug-225 handoff trunk from `refs/remotes/origin/HEAD` `3e37fb3` (L82, L96, L100; bsd r3 GO).
  - bug-216 + bug-227 `7aed8df` (L94, L97, L99, L101, L103; bsd r6 + diff check GO).
  - bug-230 `f9d1c91` (found on the merged dev tree; bsd r1 GO, M1/M2 fixed).
  - bug-212 `cc061f4` (L95, L98, L102; bsd r7 GO).
- **bug-155 fixed** (`988e96d` + `44d1a34`): clones lint like the dev tree.
- **Release commit** `af83867` (0.83.0) with release notes.
- **Live store edit:** bug-216 R4 applied to `.refmatrix/.refmatrix_ignore` before the bug-216
  merge (backup `~/.refmatrix/backups/refmatrix_ignore.refmatrix.20261114-085623`); the forced
  re-ingest has not run.
- **Leaked test daemon** (pid 89734, 20 h, throwaway store `/private/tmp/r1-hcn81cf7`) stopped;
  bug-229.
- **Bugs logged:** bug-227 (fixed), bug-228 (ac2b timing), bug-229 (test daemon leak), bug-230
  (fixed), bug-231 (graceful-stop bound under load), bug-232 (per-caller refusal remedies),
  bug-233 (STM git milestones: wrong repo's diffstat, wrong labels).
- **Ledger:** every report of this session has its INDEX / last_run / IMPRESSIONS lines
  (`be4a553`; bug-225's came with its merge). IMPRESSIONS.md is over its 50-bullet cap: fold due.

## Deploy (next action) {#deploy}

When the suite finishes, compare its failures with the known set BY E LINE: brief_real_daemon
lock, task21_1 ac6 ×2, `test_repo_hooks_in_sync` baseline drift (clears at the hook re-install),
possibly bug-228 / bug-231 timing. Anything else stops the deploy. Then, in order (full detail in
memory `project_0830_release_ready`):

1. `git -C ~/refmatrix pull --ff-only origin master` (deploy tree clean at `6863c84`), `rmx daemon
   restart --relaunch`, `rmx version -v` (no `[DEV TREE]`), `rmx hub relaunch-fleet`; a STALE
   hub gets `rmx hub stop` + ONE `launchctl kickstart gui/$(id -u)/com.refmatrix.hub`.
2. Back up `~/.claude/commands/{save,recall}-state.md`, then COPY the new ones from
   `~/refmatrix/src/refmatrix/templates/commands/` (user's choice; not `rmx init --force`).
3. `rmx install-hooks --apply --force` in the 8 roster repos (memory `project_fleet_roster_1114`)
   behind backups of `~/.claude/hooks`, `~/.claude/settings*.json`, each repo's
   `.claude/settings.json`, `.claude/rmx-hooks.json` and `.git/hooks`; diff hook entries after;
   byte-compare `.git/hooks` with the generator (bug-209).
4. bug-216 R4: back up `catalog.read.duckdb`, `facts.log`, `active`, then `rmx reingest --force
   --no-sessions` (announced); add the bug-216 → bug-185 order edge in the registry.
5. Q2: drop the `CLAUDE.md` line from every other fleet store's `.refmatrix_ignore` (each backed
   up, announced); report each store's recount (`scripts/check-rel-landing.py`).
6. Then `rmx save-state` again so the handoff records the deploy.

## Open {#open}

- **Questions:** none open (next id Q19 in `workflow/open-questions.md`).
- **After the deploy:** merge the 7 frozen spec branches (T0 `fa1227d`, T2 `0fd8a2f`, T3a
  `8e8e307`, T3b `5559d20`, T3c `01c1f63`, T4 `b409d98`, T56 `fa1af7d`; T56 before T3a, expect an
  ADR-0004 conflict) → G27 bookkeeping and the POP rewrite → the goal text for the user.
- **Follow-ups logged:** bug-229 (session reaper for test daemons), bug-231 (measure the stop,
  not the seconds), bug-232, bug-233; IMPRESSIONS fold; `spec-t3ab-r3` report's ledger lines
  come with the spec-branch merges.
- **Throwaway clones left on `/Volumes/littlebig`:** `refmatrix-bug212-mut4`, `bsd216-r3`..`r6`,
  `bsd230-r1`, plus the five task clones; remove when no longer wanted (look before deleting).
- **Not pushed:** dev master is ~300 commits ahead of `origin/main` (the user pushes).
- **Uninvestigated:** `~/.claude` holds unstaged deletions (231 at last count).

## Resume {#resume}

1. `/recall-state`; read this file and memory `project_0830_release_ready`.
2. Read the suite log's tail; if it finished, do `#deploy`. If it did not, rerun it once
   (`.venv-eval/bin/python -m pytest -q -p no:cacheprovider > workflow/review-output/release-0.83.0-full.log 2>&1`).
3. Never run the dev-venv `rmx` against the live store before the deploy: the dev tree is
   already 0.83.0.
