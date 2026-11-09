---
gmd: "0.1"
id: bsd-plan26-27-spec-review-r1-96feccd
title: "ch-bsd spec review r1 — plan-26 (26.0-26.9) and plan-27 (27.0-27.6): DIRTY 4B/10S/9M; 26.6/26.7 re-specify approved plan-19 tasks 19.3/19.4"
severity: BULLSHIT
plan: plan-26-memory-organisation
task: 26.0-26.9, 27.0-27.6
tags: [bsd, spec-review, plan-26, plan-27, memory, memory-dir, compile, subjects]
---

# ch-bsd findings — spec review r1, plan-26 + plan-27 {#root}

**Commits reviewed:** `2f4a1df` (plan-26/27 drafts) + `d0097cd`/`96feccd` (task 26.9, added during the run)
**Date:** 2026-11-09T00:07:19-0800
**Author:** Todd Holley / Opus 5.5 / orchestrator (plan drafting) + ch-architect
**Mode:** pre-implementation spec review. Nothing in `src/` changed. Code claims were checked against
`src/` at `2f4a1df`. Probes ran on throwaway copies under short `mkdtemp()` roots with `HOME`
pointed at a temp dir. No live memory dir and no live store was written.

rel: contradicts -> [[feedback_decay_never_loses_knowledge]]
rel: contradicts -> [[feedback_converge_repeated_shapes]]
rel: depends-on -> [[plan-26-memory-organisation]]
rel: depends-on -> [[plan-27-memory-fleet-rollout]]

## Claims verified TRUE against code {#verified}

- Identity is the frontmatter id: `store.add_memory(name=doc.doc_id…)` is at `ingest_gmd.py:956`
  (the plan says 955). The walk is recursive: `collect_gmd_files` uses `rglob`
  (`ingest_gmd.py:1386`).
- The hash gate is keyed by NAME (`ingest_gmd.py:44,860`). **Probe (HEAD, throwaway store):**
  ingest `a/x.md`, move it unchanged to `b/x.md`, re-bridge. The report says
  `0 node(s)`. The memory row's `source_path` and every anchor's (`x#root`, `x#one`, `x#two`)
  `entities.path` still say `a/x.md`. 26.2 AC-1 is RED-able on the production CLI.
- The forget-path claims hold. The bridge never calls `mark_tracked`. `watch.is_relevant` drops
  any dot segment, so `.claude` is never synced. The eight daemon plists' WorkingDirectories are
  project roots, and none is a memdir.
- The handoff paths match: the writer is at `handoff.py:371-373`, the reader at `:491`, and the
  index link at `:228`. The recents glob at `:104` is top-level `*.md` only. The plan says "plus
  `impressions/`", which is wrong for this site (see M3).
- **viascope index wipe, reproduced** on a copy of the resolved dir. `memory_index.collect`
  finds 3 entries (the impressions). `check` returns False. `write` turns 157 lines / 61 links
  into **1 line** (the impressions pointer). The `if not entries` guard does not fire.
- `apply_plan` only unlinks leaves (`consolidate.py:630-645`) and never retires a subject.
  Subjects are `protected=True` (`store.py:2716`).

## Findings {#findings}

### BULLSHIT: 26.6 and 26.7 re-specify APPROVED plan-19 tasks 19.4 and 19.3 under new names, and break plan-22's anchor {#b1}

**File:** `task-26.6-compile-subject-hygiene.md#requirements`, `task-26.7-memory-index-by-subject.md#requirements`
**What:** 26.6 adds `metadata.retired_at`/`retired_by` on compiled subjects that have zero leaves,
un-retires them on return, and stamps compile staleness. 26.7 groups `MEMORY.md` by compiled
subject.
**Why it's bullshit:** plan-19 is APPROVED (plan-of-plans row 19), and it already specifies all of this:
- 19.4 R5 marks those subjects `metadata.stale = true` + `stale_since`, unmarks a subject that
  regains members, hides it from recall and the index, and sends removal only through plan-22.
- 19.4 R6 gives unlabeled clusters stable names (today's `unlabeled_N` rows).
- 19.4 R1 schedules compile, and 19.4 R3 has compile regenerate the index.
- 19.3 is "MEMORY.md is grouped by compiled subject and folded by value", with hooks preserved
  (R6).

Plan-26 and plan-27 never mention plan-19: there are zero hits for `19.3`, `19.4` or `plan-19`.
Plan-22's `stale-subject` audit class (`task-22.1a#r1`) keys on 19.4's `stale` mark. So 26.6's
"physical removal waits for plan-22's audited path" points at an audit that will never see a
`retired_at` row. That is an unanchored deferral (rule 9a), and it gives two marks for one state.
**Fix:** reconcile before approval. Either 26.6/26.7 become "execute (or amend) 19.4 R5/R6 and
19.3", with `rel: implements`/`amends` edges and ONE mark (`stale`), or plan-19's tasks are
explicitly superseded and 22.1a is re-pointed. The 26.6 AC-7 label grade and the casefold fix
(AC-5) are the only parts that are new.
**Pattern match:** YES. This is two-ways-to-do-X across plans: a second spec of an approved
spec.

### BULLSHIT: `rmx memory organise <MEMDIR>` bridges into the CWD's store, not the memdir's {#b2}

**File:** `task-26.5-memory-organise-verb.md#requirements` (AC-1, AC-4, AC-8), `task-27.0#requirements` AC-6, `task-27.2`, `task-27.4`
**What:** The verb takes an arbitrary MEMDIR, and `--apply` ends with `_sync_memory_dir`.
**Why it's bullshit:** `_sync_memory_dir` calls `_ingest_gmd_sync`, which resolves the store
through `_root()` (`cli.py:87`: `REFMATRIX_ROOT`, else cwd) and the partition through
`_memory_partition_default()`. Nothing maps a memdir argument to its project. Plan-27's runs are
driven from a refmatrix session. `rmx memory organise <viascope memdir> --merge-from …` run
from that cwd would write viascope's ~178 memories into REFMATRIX's store. 27.0 AC-6 says
"dest's store daemon" but names no mechanism. AC-8 ("fail closed") only covers `Store()` opens.
**Fix:** add an AC. Resolve the store from the memdir's slug by reusing
`_root_from_projects_slug` (`cli.py:113`). That needs the UNRESOLVED path, because viascope's
resolved path is outside `~/.claude/projects`. Refuse non-zero when the cwd root disagrees.
Report `no store` (file-only) when no root matches. RED: run the verb from root A on root B's
memdir and assert no row lands in A.
**Pattern match:** YES. A resolver keyed on the wrong input; same family as IMPRESSIONS
2026-10-19 plan-4 r6.

### BULLSHIT: 26.9 R1's "same code path, no second clusterer" makes the two compiles destroy each other {#b3}

**File:** `task-26.9-impression-patterns.md#r1`, `#ac-1`
**What:** A compile scoped to the `impression` mtype proposes pattern subjects through the 26.6 path.
**Why it's bullshit:**
- `apply_plan(prune=True)` iterates EVERY `compiled_by=memory-compile` subject in the partition
  and unlinks all of its leaves (`consolidate.py:630-645`). A scoped `--apply` therefore
  un-files every project subject today. With 26.6 it would also retire them all, and the next
  full compile would retire every pattern.
- Subject identity is the slug of the label (`store.py:2703-2718`). A pattern labelled
  `daemon_ops` IS the project subject `daemon_ops`.
- The full compile already clusters impressions, because `impression` is not in
  `DEFAULT_EXCLUDE_MTYPES` (`consolidate.py:65`).
- AC-1's RED premise ("compile has no mtype-scoped selection") is false.
  `--exclude-mtype '[!i]*'` already scopes to `impression` at HEAD (fnmatch globs,
  `consolidate.py:86-90`). The only RED left is a missing flag, not behaviour.

**Fix:** stamp a `compiled_scope` on subjects. Scope prune and retire to the same scope.
Namespace the slugs (`pattern_…`). Exclude `impression` (and `tag: pattern` docs) from the
default compile. Make AC-1's RED "a scoped `--apply` leaves the other scope's subjects and
leaves untouched", which fails at HEAD.
**Pattern match:** YES. A "same path" claim that was never traced.

### BULLSHIT: regeneration and moves drop hand-curated index prose and curated hooks {#b4}

**File:** `task-26.5#requirements` AC-3, `task-27.2#requirements` AC-4, `task-27.4` AC-3, `task-27.6` AC-2, `task-26.1` AC-3
**What:** Every touched dir gets `MEMORY.md` regenerated by `memory_index.write`.
**Why it's bullshit:**
- `render` emits only entry lines and pointer lines. Measured non-link, non-blank lines that
  regeneration deletes: viascope 62 (17 headers, session log, "Active Campaign"), cliquedb 29,
  viascope2 12, cliquet 8.
- 26.1's shrink guard counts LINKS, so it passes. For viascope, 146 entries is more than 50% of
  61 links.
- Hooks are keyed by relative path (`parse_hooks`/`load_hooks`, `memory_index.py:157-214`).
  26.5 AC-3 rewrites only `.memory_hooks.json` keys. Only refmatrix and home have a sidecar.
- In cliquedb (243 top-level files move), every curated hook from an index line is orphaned and
  falls back to `_first_prose`. The tarball is the only copy left. Decay may demote; it must
  never lose.

**Fix:** key hooks by memory id (the identity principle). Make `organise` refuse to regenerate
an index that holds non-entry prose unless the prose is carried into a memory (or
`--accept-prose-loss` is passed after the user reads the diff). RED: an index-only dir with a
curated hook and a prose header, moved and regenerated, keeps both.

### SKETCHY: viascope's memdir is git-tracked inside the viascope repo {#s1}

`git -C ~/at/bdep/viascope ls-files .claude/projects` returns 147 files, including `MEMORY.md`.
`~/.claude` is itself a git repo that tracks 2 refmatrix memory files.
- `organise --apply` there produces about 146 deletions plus untracked files in a product repo.
- A tarball rollback fights git.
- A viascope branch switch swaps the memdir's layout under the store.

No spec mentions this. **Fix:** the AC-1 preview reports `git_tracked: <toplevel>`. Apply in a
tracked dir uses `git mv` and stops for the user to commit, or refuses.

### SKETCHY: the 26.4 AC-3 file rewrite makes recall-state resume from the wrong save-state {#s2}

`_latest_savestate` picks the newest file by mtime (`handoff.py:491`). Rewriting cliquedb's 4
hand-typed save-states sets their mtime to now. Measured: their mtimes are Jun 30 and Jul 26,
and the real newest, `savestate_8b1be27816f6`, is Aug 4. After 27.5, `rmx recall-state` would
resume from a July handoff, so 27.5 AC-3 "resumes" passes while resuming the wrong session.
`memory_index` already orders save-states by `created` then mtime: that is two definitions of
"newest". **Fix:** `iter_savestates` defines newest ONCE (frontmatter `updated`/`created`, then
mtime). The rewrite preserves mtime (`os.utime`). Assert it in 26.5's e2e.

### SKETCHY: the bridge walker is not the layout module; dot dirs are walked {#s3}

**Probe (HEAD):** a `.organise-rollback-1/x.md` in the memdir was ingested ("ingested 3
doc(s)"). `collect_gmd_files` runs `rglob` with only `MEMORY.md` excluded. 26.1's
`iter_memory_files` excludes dot dirs and `README.md`. The plan's "one module" lists four sites
and omits the bridge, which is the walk that matters. 26.5 AC-6 moves files aside into
`.organise-rollback-<ts>/` without saying where. Inside the memdir they stay live memories and
trip 26.2's duplicate-id refusal. **Fix:** the bridge's memory walk uses `iter_memory_files`, and
the aside dir lives under `~/.refmatrix/backups/`.

### SKETCHY: rollback overwrites post-backup edits and demotes newer same-id files {#s4}

26.5 AC-6 says "restores to archive state". A memory edited after `--apply` is overwritten. A
save-state re-saved into `savestates/` after apply is moved aside while the older top-level copy
is restored, so recall-state reads the older handoff. **Fix:** an id-aware rollback. Any
current file whose bytes differ from the archive is moved aside (outside the memdir, per S3)
before restore. Same-id conflicts are listed, not silently resolved.

### SKETCHY: 26.2 AC-2 stores a second copy of a fact, plus an unstated one-time full re-ingest {#s5}

`memory_content.metadata.source_path` already records the path. Adding `gmd_source_path` to
entity meta makes two records. Every existing hash row lacks the new key, so the first bridge
after 26.8 re-ingests every memory file in every project (refmatrix 357, cliquedb 248, …) at
SessionStart. Daemon ops resolve targets (`daemon.py:3771`), so the comparison must use
resolved paths. **Fix:** gate on the existing `source_path` (resolved) for memories and
`entities.path` for docs. State the one-time cost in 26.8 or backfill it.

### SKETCHY: the 26.6 AC-4 staleness rule nags on every release and lands in the project partition {#s6}

"Stale when its version differs" fires after every deploy, even when `consolidate.py` did not
change. The derive system already has per-pass code hashes (`_DERIVE_PASS_MODULES`,
`store.py:577`), so register `memory-compile → consolidate.py`. On post-merge stores, the memory
partition IS the project partition (`_memory_partition_default`). The stamp must stay out of
`_DERIVE_EXPECTED_PASSES` and out of the partition's `oldest_version` verdict, or the whole
graph reads derive-stale. Superseded in part by B1 (19.4).

### SKETCHY: 27.3 backs up a store that a live session is writing in-process {#s7}

bdep/thiquet has no daemon. `cli.log` shows agent `sync` writes at 2026-11-08T23:25, and
`catalog.A.duckdb` has mtime 23:25. "Tar with its daemon stopped" holds no writer. **Fix:** the
same session-boundary gate as 27.5, or tar the snapshot/replica.

### SKETCHY: 27.5's 30-minute idle fallback is not a session boundary; Q2 auto-filing has the same race {#s8}

A resumed session edits the paths it loaded from the old `MEMORY.md`. A Write recreates a
top-level file with an existing id, and 26.2 freezes the row (counted, printed only at the next
save-state). **Fix:** apply only on acknowledgement or with no live session (no Claude process
with that cwd). Q2 below.

### SKETCHY: 26.9 R4 edits a template that does not exist and puts project specifics in the neutral file {#s9}

`src/refmatrix/templates/agents/` holds only `gmd-curator.md`. The ch-bsd baseline is
cat-herder's `.claude/agents/ch-bsd.md`, which already differs from refmatrix's copy. The
neutral file says project specifics belong in `ch-bsd.local.md`. **Fix:** R4 goes into the
overlay. A baseline change, if wanted, is a cat-herder change.
**Conflict of interest:** this reviewer is the agent whose procedure R4 rewrites, and Q1 makes
it the author of the pattern rules it would then read first. Its own escalation would bump
counts it maintains. Assess R4 independently. Require that sighting counts are derived from
finding files (M8), and that the user approves every pattern doc before 0b reads it.

### SKETCHY: the 26.9 R3/AC-3 fold is not provably lossless and the cap can be gamed {#s10}

"Exactly one pattern doc" contradicts R1's multi-membership. The 50-line cap counts lines: 16
ledger lines already exceed 1000 chars, and one "consolidated bullet" can absorb everything.
45 of the 222 `- ` lines are not dated run bullets, so "the last ~20 runs" has no defined
boundary. Pattern docs are `type: impression`, so they re-enter the next scoped compile.
**Fix:** require "at least one home" with a char cap, define run boundaries by report link, and
exclude `tag: pattern` from the corpus.

### MEH: 26.1 AC-2 count {#m1}

`render` shows impressions as one pointer line, so the fixture renders 7 entry lines + 1
pointer, not "8". Assert on `collect()` (8; HEAD gives 2).

### MEH: 26.8 AC-2 arithmetic {#m2}

The 290 top-level files are 40 save-states plus 250 typed files (68+170+12). "40 save-states;
290 other" double counts.

### MEH: the plan's `#measured` misstates `_ss_recent_memories` {#m3}

`handoff.py:104` globs top-level `*.md` only. It does not glob `impressions/`.

### MEH: verb parity gaps {#m4}

`memory compile` is LEGACY (`verbs.py:1893`), yet 26.9 asks for MCP parity for `--type`.
26.6's `--include-retired` must reach `rmx_memory` (`verbs.py:1443`), but only `cli.py` is
listed.

### MEH: the bridge's waited-job branch {#m5}

`_bridge_wait_for_active_job` must carry `duplicate_ids` and `mtype_normalised` too (26.2 AC-3,
26.4 AC-1).

### MEH: MEMORY-RULES.md (user-global) is not updated {#m6}

It governs where every agent writes memories, and the folder convention never reaches it.

### MEH: 26.5 AC-2 member count {#m7}

The member count must come from the full walk including dotfiles, not from
`iter_memory_files`.

### MEH: 26.9 R2 sighting count {#m8}

A sighting count kept in curated prose is a counter read at the wrong instant. Derive it from
the `workflow/bullshit/` reports.

### MEH: ordering {#m9}

- Plan-26 has no file-overlap table against the unmerged 3.7 clone (`d02739e`, 54 commits,
  `cli.py` ±1675, `verbs.py` +1290, still DIRTY at r3). The direct overlap is small: 3.7 does not
  touch `_sync_memory_dir`, `_bridge_stats` or compile. But 26.5's verb and parity map must
  rebase on it.
- 26.9's live AC-5 (a dedicated ch-bsd run after 26.8) should not gate plan-26's close, or it
  delays plan-25's consumer bugs.
- 25.1 depends on 26.7, and 26.7 collides with 19.3 (B1). Resolve ownership before plan-25
  reads the index.

## Open questions — verdicts {#questions}

| q | verdict |
|---|---|
| 26 Q1 full convention for refmatrix | Sound for refmatrix (sidecar exists, not repo-tracked). Fleet-wide only after B2/B4/S1. |
| 26 Q2 save-state files new strays | **Change**: report-only. Moving files under a live session races its writes (S8). File them at organise or a session boundary. |
| 26 Q3 folder authoritative for `savestates/` only | Sound. |
| 26 Q4 plan-26 owns the save-state mtype | Sound (plan-25 already defers to it). The AC-3 rewrite must preserve mtime (S2). |
| 26 Q5 demote in place | Sound in substance. **Change** the mark to 19.4 R5's `stale`/`stale_since` so plan-22's audit sees it (B1). |
| 26 Q6 index shape | **Defer to 19.3** (approved: live-subject blocks, fold by value, hooks preserved). 63 headers would spend about a third of the 200-line cap. |
| 26 Q7 ADR first | Sound. The ADR must also fix: memdir→store resolution (B2), id-keyed hooks (B4), git-tracked memdirs (S1), the aside location (S3). |
| 27 Q1 viascope2 overlap | Sound. Verified: 32 memories plus `MEMORY.md`, one id overlap, and the bytes differ. |
| 27 Q2 archive the viascope2 checkout | Sound as a user action. The checkout exists. |
| 27 Q3 hooks report-only | Sound. The organise bridge covers viascope (0 save-states, no SessionStart bridge). |
| 27 Q4 home dir | Sound. `_root()` in `/Users/tholley` is `~/.refmatrix`, the home daemon `tholley-506f…`. |
| 27 Q5 enduris thiquet | Sound. Note its daemon is running now (pid 82374, `thiquet-369d4c5eeb65`). The uninstall must verify it stopped. |
| 27 Q6 ble-sniffer | Sound. |
| 26.9 Q2 project-memory patterns | Sound ("no"). 19.3 covers project memories. |

## Verdict {#verdict}

DIRTY, 23 findings (4 BULLSHIT, 10 SKETCHY, 9 MEH). Neither plan is approval-ready. B1
(reconcile with plan-19 and plan-22) is a planning decision for the user. B2, B3 and B4 are
spec ACs. The rest are AC edits.

rel: contradicts -> [[feedback_converge_repeated_shapes]]
