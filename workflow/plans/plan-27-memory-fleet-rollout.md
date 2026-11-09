---
gmd: "0.1"
id: plan-27-memory-fleet-rollout
title: "Plan 27: roll plan-26's memory organisation out to every project's memory dir, and fix the two dirs that point at the wrong project"
tags: [plan, memory, memory-dir, rollout, fleet, viascope, thiquet, cliquedb, migration]
metadata:
  node_type: plan
  status: drafting
  created: 2026-11-08
---

# Plan 27: memory fleet rollout {#root}

**Date:** 2026-11-08
**Status:** Drafting
**Location:** `workflow/plans/plan-27-memory-fleet-rollout.md`
**Depends on:** [[plan-26-memory-organisation]] merged, released AND deployed (26.8 green).
Plan 27 changes no behaviour of its own, apart from the merge mode in task 27.0. It applies the
deployed `rmx memory organise` verb dir by dir.

rel: depends-on -> [[plan-26-memory-organisation]]
rel: depends-on -> [[constitution]]
rel: implements -> [[tdd-governance]]
rel: reinforces -> [[feedback_verify_memory_by_recall_not_get]]
rel: reinforces -> [[feedback_launchd_install_force_leaves_it_unloaded]]
rel: reinforces -> [[feedback_store_calls_via_daemon]]
rel: specifies -> [[task-27.0-organise-merge-from]]
rel: specifies -> [[task-27.1-fleet-inventory]]
rel: specifies -> [[task-27.2a-index-prose-to-memories]]
rel: specifies -> [[task-27.2-viascope2-fold-and-repoint]]
rel: specifies -> [[task-27.3-thiquet-store-repoint]]
rel: specifies -> [[task-27.4-quiet-dir-migrations]]
rel: specifies -> [[task-27.5-cliquedb-at-session-boundary]]
rel: specifies -> [[task-27.6-per-store-compile-and-landing]]

## Context {#context}

### Survey, 2026-11-08 (coordinator plus architect, corrected) {#survey}

Columns: memories, top-level, save-states, store and daemon, bridge hook. The store column says
which `.refmatrix/` the project's `default_memory_dir(repo)` slug maps from. The bridge column
says whether the project has the SessionStart `ingest-gmd --as-memory` hook.

| memory dir (`~/.claude/projects/…/memory`) | mem | top | ss | store / daemon | SessionStart bridge |
|---|---|---|---|---|---|
| `-claude-tools-refmatrix` | 357 | 290 | 40 | refmatrix, supervised | yes (plan-26 does it) |
| `-bdep-cliquedb` | 248 | 243 | 63 (4 mis-typed) | cliquedb, supervised | **no** (stale hooks, `2>/dev/null \|\| true`) |
| `-bdep-cliquet` | 55 | 54 | 3 | cliquet, supervised | to inventory |
| `-bdep-viascope` (symlink → `~/at/bdep/viascope/.claude/projects/…`) | 146 | 1 | 0 | viascope, supervised | **no** |
| `-bdep-viascope2` | 32 | 32 | 0 | **no store**; repo merged into viascope 2026-04-17 (`98df0696`) | n/a |
| `-bdep-thiquet` | 34 | 34 | 13 | bdep/thiquet store, **NOT supervised**; supervised `~/enduris/thiquet` store is empty and maps to no memory dir | to inventory |
| `-bdep-ble-sniffer-mqtt` | 21 | 21 | 1 | checkout not found at `~/github/atollogy/bdep/ble-sniffer-mqtt` | n/a |
| `-bdep-portal` | 16 | 16 | 0 | no store | n/a |
| `-DataGripProjects-evolution` | 11 | 11 | 0 | no store | none |
| `-bdep-intropretor` 8, `-enduris-enduris` 8, `-enduris-shrub` 6, `-bdep-cat-herder` 6 (1 ss), `-claude-tools-gmd` 5 (1 ss), `-bdep-atlftpd` 4 (1 ss), `-bdep-atldb` 2 (2 ss), `-enduris-unified-tree-server` 2, `-bdep-orderly` 1 (1 ss) | small | | | cat-herder, atlftpd, atldb and orderly have stores; atldb and orderly are supervised | to inventory |
| `-Users-tholley` (home) | 6 | 6 | 4 (+1 non-GMD) | `~/.refmatrix`: the home daemon AND the hub's global store | to inventory |

Empty dirs (`-viascope-src-viascope`, `-viascope2-docs`) need nothing beyond being listed.

### Facts that shape the tasks {#facts}

- **A memory dir reaches a store only through the bridge.** The bridge runs inside
  `rmx save-state` (`finalize_save_state` → `_sync_memory_dir`) and from the SessionStart
  `ingest-gmd --as-memory --detach '<memdir>'` hook (`hooks.py:289-306`). cliquedb and viascope
  have neither the hook nor (in viascope's case) any save-state. viascope's 146 memories may
  never have been bridged in full. 27.1 measures this.
- **Future save-states land in `savestates/` automatically everywhere.** Every project runs the
  one deployed `~/bin/rmx`. A project with no rmx hooks only gets save-states from
  `rmx save-state` (deployed code) or from an agent writing a file by hand. The hand-written case
  is cliquedb's 4. plan-26's reader keeps reading the legacy top level and its bridge rule
  re-types them (26.3, 26.4).
- **A dir with no store still benefits from the move.** The human, and Claude Code's auto-memory
  index (`MEMORY.md`), read the layout. The organise verb runs file-only there (26.5 AC-1 reports
  `no store`).
- **viascope's layout is the precedent plan-26 adopted.** It needs `savestates/` only on first
  use, plus a `MEMORY.md` regeneration: 33 KB is over the 24 KB character budget. Its stray
  `.memory.db` (118 KB, 2026-05-01) is reported and backed up, never deleted.

## Proposed Approach {#approach}

1. **Inventory first (27.1).** Run a dry-run of `rmx memory organise` on every dir and build a
   mapping table: memdir → resolved path → store → partition → supervised? → bridge hook? Nothing
   changes in this step.
2. **Fix the two wrong mappings before migrating them.** viascope2 folds into viascope (27.2,
   using 27.0's merge mode). Supervision moves from `~/enduris/thiquet` to bdep/thiquet (27.3).
3. **Quiet dirs one at a time (27.4).** Smallest first. Back up, apply, run a recall check where
   a store exists, then move to the next dir. The home dir (global store) goes last of these.
4. **cliquedb last (27.5).** It has an active session. Stage the run, announce it on
   `proj:cliquedb:*`, and apply at its session boundary.
5. **Per STORE, not per dir (27.6).** Re-compile subjects once a store's memory dir is
   organised. Regenerate `MEMORY.md`. Report hook drift.

Every live change follows the same rules:
- **Announce and back up first.** The user hears about the change before it happens, and a backup
  lands in `~/.refmatrix/backups/memory-organise/`.
- **Daemon ops only.** Every store touch goes through daemon ops.
- **Rollback per dir.** `rmx memory organise --rollback <tarball>` is id-aware and never
  overwrites a later edit (26.5 AC-7).

Round 1 added these rules (see [[#rev-round-1]]):
- **The target store is resolved from the memdir (B2).** `--store-from-memdir` is THE default
  of every organise run (26.5 AC-1, r2 m3), and a resolved or relative memdir path is a hard
  error. The verb resolves the store from the memdir's projects slug, never from
  the session's cwd (26.5 AC-1). This matters because plan-27 is driven from a refmatrix session.
- **Hooks and prose survive regeneration (B4).** Every `MEMORY.md` regeneration carries
  hand-written prose and keeps hooks keyed by id (26.1 AC-4..AC-6). A dir whose prose would not
  fit is refused and reported. Nothing is dropped.
- **Git-tracked dirs (S1).** In a tracked memdir, the moves are staged `git mv`s in the owning
  repo, and the verb exits 3 with the exact commit command. The user commits. Today that means
  viascope's repo (147 files) and `~/.claude` (2 live refmatrix files; that repo also carries 93
  unrelated unstaged deletions, so the command is never `commit -a`).
- **The marker (r2 s2).** Plan-26's deploy leaves every un-organised dir on HEAD behaviour. The
  dir changes only when this plan's organise apply backs it up and writes `.memory-layout`. From
  then on, save-states land in `savestates/` and the new index renderer applies there.
  26.8 AC-0's pre-deploy fleet snapshot is the earliest backup of each dir's index.
- **Live sessions (S8).** A dir whose project has a live session is changed only after that
  session's explicit acknowledgement (bus or user). There is no idle timer. This applies to
  cliquedb, and also to bdep/thiquet, whose store is written in-process by a daemonless session
  (S7).

### What this plan will NOT do {#non-goals}

- No deletion of any memory dir, checkout or store directory. Retirement means backup plus a
  tombstone README plus unsupervising, and the user decides on deletion.
- No hook regeneration in other repos. 27.6 REPORTS drift (`rmx install-hooks --check` per
  project). Regenerating is the user's call, and plan-24's mod replaces the shell hooks anyway
  (Q3).
- No archiving of the viascope2 checkout. It is flagged for the user's decision.
- No commit in another repo. Tracked moves are staged, and the user commits.
- No compile or index design. 27.6 runs plan-26's 26.6 (which builds 19.4) and 26.7 (which builds
  19.3) per store.

## Task list {#tasks}

| task | what | depends on |
|------|------|------------|
| [[task-27.0-organise-merge-from]] | `rmx memory organise --merge-from <dir>`: id-reconciling fold | plan-26 deployed |
| [[task-27.1-fleet-inventory]] | dry-run every dir; memdir→store mapping; bridge coverage | plan-26 deployed |
| [[task-27.2a-index-prose-to-memories]] | convert viascope's 22,643 chars of `MEMORY.md` prose (94% of the budget), and any dir over 50%, into user-approved memories | 27.1 |
| [[task-27.2-viascope2-fold-and-repoint]] | fold viascope2 into viascope; repoint; retire the viascope2 dir | 27.0, 27.1, 27.2a |
| [[task-27.3-thiquet-store-repoint]] | supervise bdep/thiquet; retire the `~/enduris/thiquet` store | 27.1 |
| [[task-27.4-quiet-dir-migrations]] | organise each remaining dir, one at a time | 27.1 (27.3 before the thiquet dir) |
| [[task-27.5-cliquedb-at-session-boundary]] | staged, announced cliquedb migration | 27.1, 27.4 |
| [[task-27.6-per-store-compile-and-landing]] | per-store re-compile, `MEMORY.md`, hook-drift report | 27.2-27.5 |

## Acceptance for the plan {#acceptance}

- Every non-empty memory dir in [[#survey]] reads clean under `rmx memory organise --check`, or
  it is listed with a named, user-accepted reason.
- In every store-backed dir: a recall for a phrase unique to one migrated memory returns it from
  that project's store, and `rmx recall-state` resumes.
- Nothing resolves the viascope project's memory to viascope2. `rmx hub status` lists
  bdep/thiquet and not `~/enduris/thiquet`.
- A backup tarball exists for every dir touched, named in the implementation summary.
- `@ch-bsd` over the commit range (27.0 code plus the bookkeeping) is CLEAN.

## Open questions (phrased as decisions) {#open-questions}

- **Q1: if viascope2's one overlapping id (`reference_atleps01_deploy_target`) differs from
  viascope's copy, what happens?** Recommend: keep viascope's file under the id. Import
  viascope2's file as a NEW id, `reference_atleps01_deploy_target_viascope2`, with
  `rel: supersedes ->` or `rel: amends ->` pointing whichever way the newer `updated:` says
  (MEMORY-RULES amend/supersede tree). The user reads the diff before apply.
- **Q2: should the viascope2 checkout (`~/github/atollogy/bdep/viascope2`) be archived?**
  Recommend archiving it, since it was merged by subtree on 2026-04-17. This is the user's
  action, not the plan's.
- **Q3: should the stale hooks in cliquedb and viascope (no SessionStart bridge, silent
  `|| true`) be regenerated now?** Recommend reporting only and leaving them to plan-24's mod.
  Save-state's own bridge covers the migration. Each `rmx install-hooks` in a foreign repo is a
  backup-and-diff operation ([[feedback_install_hooks_no_claude_reaps]]) that should not ride a
  memory rollout.
- **Q4: should the home dir (`-Users-tholley`) be bridged into the GLOBAL store's memory
  partition?** Recommend organising its files and NOT changing what it bridges into until 27.1
  shows which partition it lands in today. The global store is the hub's.
- **Q5: what happens to the empty `~/enduris/thiquet` store and its `.obsidian/` and
  `CLAUDE.md`?** Recommend: unsupervise it, back up `.refmatrix/`, leave a tombstone README, and
  leave the directory in place for the user to decide.
- **Q6: what about `-bdep-ble-sniffer-mqtt`, whose checkout is not at the expected path?**
  Recommend organising it file-only and asking the user where the repo lives.

## Revision round 1 (2026-11-09) {#rev-round-1}

This round answers [[bsd-plan26-27-spec-review-r1-96feccd]].

rel: derives-from -> [[bsd-plan26-27-spec-review-r1-96feccd]]

| finding | change | anchor |
|---|---|---|
| B2 (verb bridges into the cwd's store) | Every run passes `--store-from-memdir`; 27.0, 27.2 and 27.4 assert the resolved store | [[#approach]], [[task-27.0-organise-merge-from#rev-round-1]], [[task-27.4-quiet-dir-migrations#rev-round-1]] |
| B4 (regeneration drops prose and hooks) | Prose is carried and hooks are keyed by id in every dir; refusal instead of loss | [[#approach]], [[task-27.2-viascope2-fold-and-repoint#rev-round-1]], [[task-27.6-per-store-compile-and-landing#rev-round-1]] |
| S1 (git-tracked memdirs) | `git mv` staged and the user commits; 27.1 inventories tracking per dir | [[#approach]], [[#non-goals]], [[task-27.1-fleet-inventory#rev-round-1]] |
| S7 (bdep/thiquet written in-process) | Explicit acknowledgement gate before backup | [[task-27.3-thiquet-store-repoint#rev-round-1]] |
| S8 (an idle timer is not a session boundary) | Explicit acknowledgement only | [[#approach]], [[task-27.5-cliquedb-at-session-boundary#rev-round-1]] |
| B1 (compile/index ownership) | 27.6 runs 26.6 and 26.7 (19.4 and 19.3) | [[#non-goals]] |
| S5 (one-time refresh) | 27.1 records `refresh_pending` per store before any run | [[task-27.1-fleet-inventory#rev-round-1]] |
| 27 Q1-Q6 verdicts | Sound, taken as written. Q5 note: the enduris daemon is running (pid 82374), and the uninstall must verify it stopped (27.3) | [[#open-questions]] |

## Revision round 2 (2026-11-09) {#rev-round-2}

Answers [[bsd-plan26-27-spec-review-r2-8af766a]].

rel: derives-from -> [[bsd-plan26-27-spec-review-r2-8af766a]]

| finding | change | anchor |
|---|---|---|
| s6 (viascope prose migration anchored to no task) | New task 27.2a, ahead of 27.2 and 27.6; user-approved conversion; lossless checker | [[#tasks]], [[task-27.2a-index-prose-to-memories]] |
| s2 (the deploy reaches dirs before this plan backs them up) | Marker gate stated; the pre-deploy fleet snapshot is named | [[#approach]] |
| m3 (`--store-from-memdir` semantics) | It is the default; bad paths are a hard error | [[#approach]] |
| m5 (`~/.claude` count; stop definition) | "2 live + 93 deleted"; exit 3 with the exact commit command | [[#approach]] |
| m6 (27.0 citations) | Fixed in 27.0 | [[task-27.0-organise-merge-from#rev-round-2]] |
