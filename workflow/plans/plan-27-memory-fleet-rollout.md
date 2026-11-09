---
gmd: "0.1"
id: plan-27-memory-fleet-rollout
title: "Plan 27: roll plan-26's memory organisation out to every project's memory dir, and fix the two dirs that point at the wrong project"
tags: [plan, memory, memory-dir, rollout, fleet, viascope, thiquet, cliquedb, migration]
metadata:
  node_type: plan
  status: approved
  created: 2026-11-08
  updated: 2026-11-09
---

# Plan 27: memory fleet rollout {#root}

**Date:** 2026-11-08
**Status:** Approved (2026-11-09, [[#approval]]). Revised 2026-11-09, rounds 1-5
([[#rev-round-5]]). ch-bsd r5 (0B/1S/6M) folded, including the user's 3ded49e decisions (Q2, Q6);
the r6-lite confirm closed r5 s1, m2 and m6 (MEH-only). Execution waits on plan-26 deployed.
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
| `-bdep-ble-sniffer-mqtt` | 21 | 21 | 1 | checkout is `~/github/atollogy/bdep/ble_sniffer_mqtt` (the slug turns `_` into `-`); **no store** (no `.refmatrix/`, confirmed by r5 probe) | n/a |
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
- **Legacy rows counted (r5 s1).** Each apply's bridge reports `moved_legacy` (26.2 AC-1b): rows
  that share a moved file's old `source_path`, refreshed with it. It must equal the count 27.1
  recorded for that store from the preview, exact; a mismatch stops the dir and logs a bug row.
  The duplicates are left in place, not merged or forgotten.

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
  Un-organised dirs keep HEAD's compaction (r3 m4), so 27.1 orders near-cap dirs earlier and
  tells viascope's sessions not to save state until 27.2.
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
- No move or deletion of the viascope2 checkout. Archiving it IS in scope (Q2, decided by the
  user 2026-11-09): after 27.2 verifies the fold, 27.2 AC-8 writes a backup tarball plus a
  tombstone and leaves the checkout in place. Moving or deleting it needs a further explicit go.
- No commit in another repo. Tracked moves are staged, and the user commits.
- No compile or index design. 27.6 runs plan-26's 26.6 (which builds 19.4) and 26.7 (which builds
  19.3) per store.

## Task list {#tasks}

| task | what | depends on |
|------|------|------------|
| [[task-27.0-organise-merge-from]] | `rmx memory organise --merge-from <dir>`: id-reconciling fold | plan-26 deployed |
| [[task-27.1-fleet-inventory]] | dry-run every dir; memdir→store mapping; bridge coverage | plan-26 deployed |
| [[task-27.2a-index-prose-to-memories]] | convert viascope's 22,643 chars of `MEMORY.md` prose (94% of the budget), and any dir over 50%, into user-approved memories | 27.1 |
| [[task-27.2-viascope2-fold-and-repoint]] | fold viascope2 into viascope; repoint; retire the viascope2 dir; archive the viascope2 checkout (tarball + tombstone, nothing moved) | 27.0, 27.1, 27.2a |
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
- A backup tarball exists for every dir touched, named in the implementation summary, and one
  for the viascope2 checkout (27.2 AC-8).
- Every apply's bridge reports `moved_legacy` equal to 27.1's projected count for that store,
  exact (r5 s1).
- `@ch-bsd` over the commit range (27.0 code plus the bookkeeping) is CLEAN.

## Open questions (phrased as decisions) {#open-questions}

- **Q1: if viascope2's one overlapping id (`reference_atleps01_deploy_target`) differs from
  viascope's copy, what happens?** DECIDED (orchestrator, r4; recommendation adopted): keep viascope's file under the id. Import
  viascope2's file as a NEW id, `reference_atleps01_deploy_target_viascope2`, with
  `rel: supersedes ->` or `rel: amends ->` pointing whichever way the newer `updated:` says
  (MEMORY-RULES amend/supersede tree). The user reads the diff before apply.
- **Q2: should the viascope2 checkout (`~/github/atollogy/bdep/viascope2`) be archived?**
  Recommend archiving it, since it was merged by subtree on 2026-04-17. **DECIDED (user,
  2026-11-09): okay** — archive it after 27.2 verifies the fold (backup first; never delete without
  a further explicit go).
- **Q3: should the stale hooks in cliquedb and viascope (no SessionStart bridge, silent
  `|| true`) be regenerated now?** DECIDED (r4): report only, and leave them to plan-24's mod.
  Save-state's own bridge covers the migration. Each `rmx install-hooks` in a foreign repo is a
  backup-and-diff operation ([[feedback_install_hooks_no_claude_reaps]]) that should not ride a
  memory rollout.
- **Q4: should the home dir (`-Users-tholley`) be bridged into the GLOBAL store's memory
  partition?** DECIDED (r4): organise its files, and do NOT change what it bridges into until 27.1
  shows which partition it lands in today. The global store is the hub's.
- **Q5: what happens to the empty `~/enduris/thiquet` store and its `.obsidian/` and
  `CLAUDE.md`?** DECIDED (r4): unsupervise it, back up `.refmatrix/`, leave a tombstone README, and
  leave the directory in place for the user to decide.
- **Q6: what about `-bdep-ble-sniffer-mqtt`, whose checkout is not at the expected path?**
  **ANSWERED (user, 2026-11-09):** the repo is `~/github/atollogy/bdep/ble_sniffer_mqtt`
  (origin `bitbucket.org:at0l/ble_sniffer_mqtt`; the memory-dir slug turns `_` into `-`). It has
  no `.refmatrix/` store, so it stays organised file-only (`no store`), now with the checkout named.

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

## Revision round 3 (2026-11-09) {#rev-round-3}

Answers [[bsd-plan26-27-spec-review-r3-696c3cb]].

| finding | change | anchor |
|---|---|---|
| s2 (the refresh was measured on memdir copies) | Measured on the live path against a store-snapshot copy | [[task-27.1-fleet-inventory#rev-round-3]] |
| s3 (27.2a checker) | Artifact, RED cases, verifiable ADR branch, anchored headers | [[task-27.2a-index-prose-to-memories#rev-round-3]] |
| m1 (27.1 duplicates; 27.6 landing table) | Fixed | [[task-27.1-fleet-inventory#rev-round-3]], [[task-27.6-per-store-compile-and-landing#rev-round-3]] |
| m4 (no compaction until organised) | Headroom ordering; viascope notice | [[#approach]] |
| 27 Q1-Q6 r3 verdicts | All sound. Q6: ble-sniffer is `no store`, not exit 2 | [[#open-questions]] |

## Revision round 4 (2026-11-09) {#rev-round-4}

Answers [[bsd-plan26-27-spec-review-r4-f89e640]].

| finding | change | anchor |
|---|---|---|
| r4 verdicts on 27 Q1, Q3, Q4, Q5 | Recorded as DECIDED (recommendations adopted) | [[#open-questions]] |
| 27 Q2, Q6 | Open at r4; DECIDED by the user at 3ded49e (Q2: archive after 27.2 verifies, no delete; Q6: `~/github/atollogy/bdep/ble_sniffer_mqtt`, `no store`), carried into the text at r5 | [[#open-questions]], [[#rev-round-5]] |
| m2 (27.2a checker) | Whole-line multiset match per block | [[task-27.2a-index-prose-to-memories#rev-round-4]] |

## Revision round 5 (2026-11-09) {#rev-round-5}

Answers [[bsd-plan26-27-spec-review-r5-3ded49e]] (DIRTY 0B/1S/6M). No user decision remains:
the user's 3ded49e decisions (Q2, Q6) are carried into the text here.

rel: derives-from -> [[bsd-plan26-27-spec-review-r5-3ded49e]]

| finding | change | anchor |
|---|---|---|
| s1 (legacy rows in every pre-alias store go dead-path, uncounted) | 27.1 records projected `moved_legacy` and the legacy-duplicate count per store; every apply must match it, exact | [[#approach]], [[#acceptance]], [[task-27.1-fleet-inventory#rev-round-5]] |
| m6 (3ded49e not carried) | `#non-goals` viascope2 line flipped; 27.2 AC-6 and new AC-8 archive the checkout (tarball under `~/.refmatrix/backups/memory-organise/`, tombstone `RETIRED.md`, nothing moved or deleted); r4 table Q2/Q6 rows marked decided; survey and 27.1 AC-4 name `~/github/atollogy/bdep/ble_sniffer_mqtt`, `no store`; 27.1 "latent wipe" restated as prose loss (r4 s1) | [[#non-goals]], [[#survey]], [[#tasks]], [[#rev-round-4]], [[task-27.2-viascope2-fold-and-repoint#rev-round-5]], [[task-27.1-fleet-inventory#rev-round-5]] |
| s1, m1-m5 (plan-26 text) | Folded in plan-26 | [[plan-26-memory-organisation#rev-round-5]] |

## Approval (2026-11-09) {#approval}

Approved on the ch-bsd focused confirm r6-lite at `d396317`
([[bsd-plan26-27-spec-confirm-r6-lite-d396317]]): MEH-only, 0B/0S/2M. r5 m6 (the 3ded49e
decisions) is closed in text and buildable.

rel: derives-from -> [[bsd-plan26-27-spec-confirm-r6-lite-d396317]]

- **n1** and **n2** land in plan-26's task 26.2
  ([[task-26.2-bridge-move-safety#impl-notes-r6]]). n2 matters here: viascope's symlinked memdir
  is the case where an id row lands in `stale_before` and its legacy rows still count in
  `moved_legacy`. 27.1 AC-6 already counts every row on a planned move's from-path, so its
  wording needed no change.
- Every task in [[#tasks]] (27.0, 27.1, 27.2a, 27.2-27.6) has its spec under
  `workflow/plans/plan-27-memory-fleet-rollout-tasks/`.
